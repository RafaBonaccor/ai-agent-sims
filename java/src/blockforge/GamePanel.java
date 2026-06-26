package blockforge;

import java.awt.AWTException;
import java.awt.Color;
import java.awt.Cursor;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.GradientPaint;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.LinearGradientPaint;
import java.awt.Point;
import java.awt.Rectangle;
import java.awt.RenderingHints;
import java.awt.Robot;
import java.awt.Toolkit;
import java.awt.event.FocusAdapter;
import java.awt.event.FocusEvent;
import java.awt.event.KeyAdapter;
import java.awt.event.KeyEvent;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import javax.swing.Timer;

public final class GamePanel extends JPanel {
    private static final int PANEL_WIDTH = 1280;
    private static final int PANEL_HEIGHT = 800;
    private static final double MOVE_SPEED = 4.1;
    private static final double GRAVITY = 20.0;
    private static final double JUMP_SPEED = 8.8;
    private static final double STEP_HEIGHT = 1.15;
    private static final double VOID_DEATH_Y = -10.0;
    private static final double RESPAWN_DELAY = 1.1;
    private static final double INTERACT_RANGE = 4.75;
    private static final double PLAYER_HEIGHT = 1.7;
    private static final double PLAYER_RADIUS = 0.30;
    private static final double COLLISION_EPSILON = 0.0001;
    private static final double CORNER_SLIDE_DISTANCE = 0.12;
    private static final int HORIZONTAL_DEPENETRATION_STEPS = 8;
    private static final double HORIZONTAL_ESCAPE_RADIUS = 1.25;
    private static final double HORIZONTAL_ESCAPE_STEP = 0.05;
    private static final int HORIZONTAL_ESCAPE_SAMPLES = 32;
    private static final double FIRST_PERSON_EYE_HEIGHT = 1.55;
    private static final double FIRST_PERSON_PITCH_LIMIT = 1.48;
    private static final int VIEW_RADIUS = 13;

    private World world = new World(22);
    private final Player player = new Player();
    private final Set<Integer> pressedKeys = new HashSet<>();
    private final BlockType[] hotbarBlocks = BlockType.values();
    private final Point mousePoint = new Point(-10_000, -10_000);
    private final Cursor defaultCursor = Cursor.getDefaultCursor();
    private final Cursor hiddenCursor = createHiddenCursor();
    private final Robot mouseLookRobot = createMouseLookRobot();
    private final IsometricWorldRenderer isometricWorldRenderer = new IsometricWorldRenderer();
    private final FirstPersonWorldRenderer firstPersonWorldRenderer = new FirstPersonWorldRenderer();
    private final Timer timer;

    private long lastFrameNanos = System.nanoTime();
    private double cameraYaw = Math.toRadians(35);
    private double cameraPitch = -0.1;
    private double respawnCountdown = 0;
    private boolean jumpQueued = false;
    private int deathCount = 0;
    private int activeBlockIndex = 0;
    private boolean mouseCaptureActive = false;
    private boolean ignoreWarpedMouseEvent = false;
    private boolean paused = false;
    private boolean autoStepEnabled = false;
    private PauseAction hoveredPauseAction = null;
    private SelectionTarget selectedTarget;
    private ViewMode viewMode = ViewMode.SUPERIOR;
    private final Path savePath = SaveGame.defaultPath();
    private String notice =
        "Sandbox Java voxel: Esc pausa, F6 salva, F9 carica, V cambia camera.";

    public GamePanel() {
        setPreferredSize(new Dimension(PANEL_WIDTH, PANEL_HEIGHT));
        setFocusable(true);
        setFocusTraversalKeysEnabled(false);
        setBackground(new Color(180, 220, 255));

        respawnPlayer();

        addKeyListener(new InputHandler());
        addFocusListener(new FocusAdapter() {
            @Override
            public void focusLost(FocusEvent event) {
                if (viewMode == ViewMode.FIRST_PERSON) {
                    setFirstPersonMouseCapture(false);
                }
            }

            @Override
            public void focusGained(FocusEvent event) {
                if (!paused && viewMode == ViewMode.FIRST_PERSON) {
                    setFirstPersonMouseCapture(true);
                }
            }
        });

        MouseAdapter mouseHandler = new MouseAdapter() {
            @Override
            public void mouseMoved(MouseEvent event) {
                handleMouseMove(event);
            }

            @Override
            public void mouseDragged(MouseEvent event) {
                handleMouseMove(event);
            }

            @Override
            public void mouseExited(MouseEvent event) {
                mousePoint.setLocation(-10_000, -10_000);
                hoveredPauseAction = null;
                if (viewMode == ViewMode.SUPERIOR) {
                    selectedTarget = null;
                }
                repaint();
            }

            @Override
            public void mousePressed(MouseEvent event) {
                requestFocusInWindow();
                if (paused) {
                    handlePauseMenuClick(event.getPoint());
                    return;
                }
                if (viewMode == ViewMode.FIRST_PERSON) {
                    setFirstPersonMouseCapture(true);
                }

                handleMouseMove(event);
                if (SwingUtilities.isLeftMouseButton(event)) {
                    tryMineSelectedCell();
                } else if (SwingUtilities.isRightMouseButton(event)) {
                    tryPlaceSelectedCell();
                }
            }
        };

        addMouseListener(mouseHandler);
        addMouseMotionListener(mouseHandler);

        timer = new Timer(16, event -> {
            tick();
            repaint();
        });
        timer.start();

        SwingUtilities.invokeLater(this::requestFocusInWindow);
    }

    @Override
    protected void paintComponent(Graphics graphics) {
        super.paintComponent(graphics);
        Graphics2D g2 = (Graphics2D) graphics.create();
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);

        drawSky(g2);
        if (viewMode == ViewMode.SUPERIOR) {
            isometricWorldRenderer.drawWorld(g2, world, player, cameraYaw, VIEW_RADIUS, getWidth(), getHeight());
            isometricWorldRenderer.drawSelection(g2, selectedTarget);
            isometricWorldRenderer.drawPlayer(g2, player, cameraYaw, getWidth(), getHeight());
        } else {
            firstPersonWorldRenderer.drawWorld(g2, world, player, cameraYaw, cameraPitch, getWidth(), getHeight());
            firstPersonWorldRenderer.drawCrosshair(g2, getWidth(), getHeight());
        }
        drawHud(g2);

        g2.dispose();
    }

    private void tick() {
        long now = System.nanoTime();
        double delta = Math.min((now - lastFrameNanos) / 1_000_000_000.0, 0.05);
        lastFrameNanos = now;

        if (paused) {
            return;
        }

        if (respawnCountdown > 0) {
            selectedTarget = null;
            respawnCountdown = Math.max(0, respawnCountdown - delta);
            player.verticalVelocity -= GRAVITY * delta;
            player.y += player.verticalVelocity * delta;
            if (respawnCountdown == 0) {
                respawnPlayer();
                notice = "Respawn completato.";
            }
            return;
        }

        updateCamera(delta);
        resolveHorizontalPenetration();
        updateMovement(delta);
        applyGravity(delta);
        updateSelectionTarget();

        if (player.y < VOID_DEATH_Y) {
            deathCount += 1;
            selectedTarget = null;
            notice = "Sei caduto nel vuoto. Respawn...";
            respawnCountdown = RESPAWN_DELAY;
            player.verticalVelocity = -2.0;
            player.onGround = false;
        }
    }

    private void handleMouseMove(MouseEvent event) {
        if (paused) {
            hoveredPauseAction = pauseActionAt(event.getPoint());
            repaint();
            return;
        }

        mousePoint.setLocation(event.getPoint());
        if (viewMode == ViewMode.FIRST_PERSON) {
            if (mouseCaptureActive && mouseLookRobot != null) {
                if (ignoreWarpedMouseEvent) {
                    ignoreWarpedMouseEvent = false;
                    return;
                }

                int deltaX = event.getX() - getWidth() / 2;
                int deltaY = event.getY() - getHeight() / 2;
                if (deltaX != 0 || deltaY != 0) {
                    cameraYaw -= deltaX * 0.0045;
                    cameraPitch = clamp(
                        cameraPitch - deltaY * 0.0035,
                        -FIRST_PERSON_PITCH_LIMIT,
                        FIRST_PERSON_PITCH_LIMIT
                    );
                    updateSelectionTarget();
                    centerMousePointer();
                    repaint();
                }
                return;
            }

            int deltaX = event.getX() - getWidth() / 2;
            int deltaY = event.getY() - getHeight() / 2;
            cameraYaw -= deltaX * 0.0025;
            cameraPitch = clamp(
                cameraPitch - deltaY * 0.002,
                -FIRST_PERSON_PITCH_LIMIT,
                FIRST_PERSON_PITCH_LIMIT
            );
        }

        updateSelectionTarget();
        repaint();
    }

    private void updateCamera(double delta) {
        double rotateSpeed = 1.7;
        if (viewMode == ViewMode.FIRST_PERSON) {
            if (pressedKeys.contains(KeyEvent.VK_Q)) {
                cameraYaw += rotateSpeed * delta;
            }
            if (pressedKeys.contains(KeyEvent.VK_E)) {
                cameraYaw -= rotateSpeed * delta;
            }
            if (pressedKeys.contains(KeyEvent.VK_UP)) {
                cameraPitch = clamp(cameraPitch + rotateSpeed * 0.55 * delta, -FIRST_PERSON_PITCH_LIMIT, FIRST_PERSON_PITCH_LIMIT);
            }
            if (pressedKeys.contains(KeyEvent.VK_DOWN)) {
                cameraPitch = clamp(cameraPitch - rotateSpeed * 0.55 * delta, -FIRST_PERSON_PITCH_LIMIT, FIRST_PERSON_PITCH_LIMIT);
            }
            return;
        }

        if (pressedKeys.contains(KeyEvent.VK_Q)) {
            cameraYaw -= rotateSpeed * delta;
        }
        if (pressedKeys.contains(KeyEvent.VK_E)) {
            cameraYaw += rotateSpeed * delta;
        }
    }

    private void updateMovement(double delta) {
        double moveX = 0;
        double moveZ = 0;

        double forwardX = Math.cos(cameraYaw);
        double forwardZ = Math.sin(cameraYaw);
        double rightX = Math.sin(cameraYaw);
        double rightZ = -Math.cos(cameraYaw);

        if (pressedKeys.contains(KeyEvent.VK_W)) {
            moveX += forwardX;
            moveZ += forwardZ;
        }
        if (pressedKeys.contains(KeyEvent.VK_S)) {
            moveX -= forwardX;
            moveZ -= forwardZ;
        }
        if (pressedKeys.contains(KeyEvent.VK_A)) {
            moveX -= rightX;
            moveZ -= rightZ;
        }
        if (pressedKeys.contains(KeyEvent.VK_D)) {
            moveX += rightX;
            moveZ += rightZ;
        }

        double length = Math.hypot(moveX, moveZ);
        if (length > 0) {
            moveX = moveX / length * MOVE_SPEED * delta;
            moveZ = moveZ / length * MOVE_SPEED * delta;
            tryMove(moveX, 0);
            tryMove(0, moveZ);
        }

        if (jumpQueued && player.onGround) {
            player.verticalVelocity = JUMP_SPEED;
            player.onGround = false;
        }
        jumpQueued = false;
    }

    private void tryMove(double dx, double dz) {
        double nextX = player.x + dx;
        double nextZ = player.z + dz;
        if (canOccupy(nextX, player.y, nextZ)) {
            player.x = nextX;
            player.z = nextZ;
            return;
        }

        if (tryCornerSlide(dx, dz)) {
            return;
        }

        if (!autoStepEnabled) {
            return;
        }

        double steppedY = stepUpYAt(nextX, player.y, nextZ);
        if (Double.isNaN(steppedY)) {
            return;
        }

        if (!canOccupy(nextX, steppedY, nextZ)) {
            return;
        }

        player.x = nextX;
        player.z = nextZ;
        player.y = steppedY;
        player.verticalVelocity = 0;
        player.onGround = false;
    }

    private boolean tryCornerSlide(double dx, double dz) {
        if (dx != 0 && dz != 0) {
            return false;
        }

        if (dx != 0) {
            return trySlideTo(player.x + dx, player.z + CORNER_SLIDE_DISTANCE) ||
                trySlideTo(player.x + dx, player.z - CORNER_SLIDE_DISTANCE);
        }

        if (dz != 0) {
            return trySlideTo(player.x + CORNER_SLIDE_DISTANCE, player.z + dz) ||
                trySlideTo(player.x - CORNER_SLIDE_DISTANCE, player.z + dz);
        }

        return false;
    }

    private boolean trySlideTo(double x, double z) {
        if (!canOccupy(x, player.y, z)) {
            return false;
        }

        player.x = x;
        player.z = z;
        return true;
    }

    private double stepUpYAt(double centerX, double feetY, double centerZ) {
        double minX = centerX - PLAYER_RADIUS;
        double maxX = centerX + PLAYER_RADIUS;
        double minZ = centerZ - PLAYER_RADIUS;
        double maxZ = centerZ + PLAYER_RADIUS;
        int startX = (int) Math.floor(minX);
        int endX = (int) Math.floor(maxX);
        int startZ = (int) Math.floor(minZ);
        int endZ = (int) Math.floor(maxZ);
        int minBlockY = Math.max(world.minBlockY(), (int) Math.floor(feetY));
        int maxBlockY = Math.min(world.maxBlockY(), (int) Math.floor(feetY + STEP_HEIGHT));

        double bestStepY = Double.NaN;
        for (int x = startX; x <= endX; x += 1) {
            for (int z = startZ; z <= endZ; z += 1) {
                if (!circleOverlapsBlockXZ(centerX, centerZ, x, z)) {
                    continue;
                }
                for (int y = minBlockY; y <= maxBlockY; y += 1) {
                    if (!world.hasBlock(x, y, z)) {
                        continue;
                    }

                    double topY = y + 1.0;
                    if (topY <= feetY + COLLISION_EPSILON || topY - feetY > STEP_HEIGHT) {
                        continue;
                    }

                    if (Double.isNaN(bestStepY) || topY > bestStepY) {
                        bestStepY = topY;
                    }
                }
            }
        }
        return bestStepY;
    }

    private void applyGravity(double delta) {
        double supportY = centerSupportYAtOrBelow(player.x, player.z, player.y + COLLISION_EPSILON);
        if (!Double.isNaN(supportY) && player.y <= supportY + COLLISION_EPSILON && player.verticalVelocity <= 0) {
            player.y = supportY;
            player.verticalVelocity = 0;
            player.onGround = true;
            resolveHorizontalPenetration();
            return;
        }

        player.onGround = false;
        player.verticalVelocity -= GRAVITY * delta;
        double nextY = player.y + player.verticalVelocity * delta;

        if (player.verticalVelocity > 0 && !canOccupy(player.x, nextY, player.z)) {
            player.verticalVelocity = 0;
            return;
        }

        if (!Double.isNaN(supportY) && nextY <= supportY) {
            player.y = supportY;
            player.verticalVelocity = 0;
            player.onGround = true;
            resolveHorizontalPenetration();
            return;
        }

        player.y = nextY;
        resolveHorizontalPenetration();
    }

    private double centerSupportYAtOrBelow(double centerX, double centerZ, double maxTopY) {
        int cellX = (int) Math.floor(centerX);
        int cellZ = (int) Math.floor(centerZ);
        int maxBlockY = Math.min(world.maxBlockY(), (int) Math.floor(maxTopY - 1.0 + COLLISION_EPSILON));

        for (int y = maxBlockY; y >= world.minBlockY(); y -= 1) {
            if (world.hasBlock(cellX, y, cellZ)) {
                return y + 1.0;
            }
        }
        return Double.NaN;
    }

    private void resolveHorizontalPenetration() {
        for (int step = 0; step < HORIZONTAL_DEPENETRATION_STEPS; step += 1) {
            HorizontalPush push = findDeepestHorizontalPush();
            if (push == null) {
                return;
            }
            player.x += push.x();
            player.z += push.z();
        }

        if (!canOccupy(player.x, player.y, player.z)) {
            moveToNearestFreeHorizontalPosition();
        }
    }

    private void moveToNearestFreeHorizontalPosition() {
        double originX = player.x;
        double originZ = player.z;
        int rings = (int) Math.ceil(HORIZONTAL_ESCAPE_RADIUS / HORIZONTAL_ESCAPE_STEP);

        for (int ring = 1; ring <= rings; ring += 1) {
            double radius = ring * HORIZONTAL_ESCAPE_STEP;
            for (int sample = 0; sample < HORIZONTAL_ESCAPE_SAMPLES; sample += 1) {
                double angle = Math.PI * 2.0 * sample / HORIZONTAL_ESCAPE_SAMPLES;
                double candidateX = originX + Math.cos(angle) * radius;
                double candidateZ = originZ + Math.sin(angle) * radius;
                if (canOccupy(candidateX, player.y, candidateZ)) {
                    player.x = candidateX;
                    player.z = candidateZ;
                    return;
                }
            }
        }
    }

    private HorizontalPush findDeepestHorizontalPush() {
        double bodyMinY = player.y + COLLISION_EPSILON;
        double bodyMaxY = player.y + PLAYER_HEIGHT - COLLISION_EPSILON;

        if (bodyMaxY < world.minBlockY() || bodyMinY > world.maxBlockY() + 1.0) {
            return null;
        }

        int startX = (int) Math.floor(player.x - PLAYER_RADIUS);
        int endX = (int) Math.floor(player.x + PLAYER_RADIUS);
        int startY = Math.max(world.minBlockY(), (int) Math.floor(bodyMinY));
        int endY = Math.min(world.maxBlockY(), (int) Math.floor(bodyMaxY));
        int startZ = (int) Math.floor(player.z - PLAYER_RADIUS);
        int endZ = (int) Math.floor(player.z + PLAYER_RADIUS);

        HorizontalPush bestPush = null;
        double bestDistance = 0;

        for (int blockX = startX; blockX <= endX; blockX += 1) {
            for (int blockY = startY; blockY <= endY; blockY += 1) {
                for (int blockZ = startZ; blockZ <= endZ; blockZ += 1) {
                    if (!world.hasBlock(blockX, blockY, blockZ)) {
                        continue;
                    }
                    if (!verticalOverlapsBlock(bodyMinY, bodyMaxY, blockY)) {
                        continue;
                    }
                    HorizontalPush push = circlePushOutOfBlockXZ(player.x, player.z, blockX, blockZ);
                    if (push == null) {
                        continue;
                    }

                    double distance = push.x() * push.x() + push.z() * push.z();
                    if (distance <= bestDistance) {
                        continue;
                    }
                    bestDistance = distance;
                    bestPush = push;
                }
            }
        }

        return bestPush;
    }

    private HorizontalPush circlePushOutOfBlockXZ(double centerX, double centerZ, int blockX, int blockZ) {
        double closestX = clamp(centerX, blockX, blockX + 1.0);
        double closestZ = clamp(centerZ, blockZ, blockZ + 1.0);
        double deltaX = centerX - closestX;
        double deltaZ = centerZ - closestZ;
        double distanceSquared = deltaX * deltaX + deltaZ * deltaZ;

        if (distanceSquared > 0) {
            double distance = Math.sqrt(distanceSquared);
            if (distance >= PLAYER_RADIUS) {
                return null;
            }
            double pushDistance = PLAYER_RADIUS - distance + COLLISION_EPSILON;
            return new HorizontalPush(deltaX / distance * pushDistance, deltaZ / distance * pushDistance);
        }

        double pushLeft = blockX - PLAYER_RADIUS - centerX - COLLISION_EPSILON;
        double pushRight = blockX + 1.0 + PLAYER_RADIUS - centerX + COLLISION_EPSILON;
        double pushBack = blockZ - PLAYER_RADIUS - centerZ - COLLISION_EPSILON;
        double pushForward = blockZ + 1.0 + PLAYER_RADIUS - centerZ + COLLISION_EPSILON;

        double absLeft = Math.abs(pushLeft);
        double absRight = Math.abs(pushRight);
        double absBack = Math.abs(pushBack);
        double absForward = Math.abs(pushForward);
        double minPush = Math.min(Math.min(absLeft, absRight), Math.min(absBack, absForward));

        if (minPush == absLeft) {
            return new HorizontalPush(pushLeft, 0);
        }
        if (minPush == absRight) {
            return new HorizontalPush(pushRight, 0);
        }
        if (minPush == absBack) {
            return new HorizontalPush(0, pushBack);
        }
        return new HorizontalPush(0, pushForward);
    }

    private void respawnPlayer() {
        respawnCountdown = 0;
        jumpQueued = false;
        pressedKeys.remove(KeyEvent.VK_SPACE);
        player.respawn(world.findSpawnPoint());
        updateSelectionTarget();
    }

    private void toggleViewMode() {
        viewMode = viewMode == ViewMode.SUPERIOR ? ViewMode.FIRST_PERSON : ViewMode.SUPERIOR;
        updateSelectionTarget();
        if (viewMode == ViewMode.FIRST_PERSON) {
            setFirstPersonMouseCapture(true);
            notice = "Camera: prima persona. Mouse agganciato; premi Esc per liberarlo.";
        } else {
            setFirstPersonMouseCapture(false);
            notice = "Camera: superiore. Mondo voxel condiviso.";
        }
    }

    private void setFirstPersonMouseCapture(boolean active) {
        boolean canCapture = active && mouseLookRobot != null && isShowing();
        mouseCaptureActive = canCapture;
        ignoreWarpedMouseEvent = false;
        setCursor(canCapture ? hiddenCursor : defaultCursor);
        if (canCapture) {
            centerMousePointer();
        }
    }

    private void centerMousePointer() {
        if (mouseLookRobot == null || !isShowing() || getWidth() <= 0 || getHeight() <= 0) {
            return;
        }

        Point centerOnScreen = new Point(getWidth() / 2, getHeight() / 2);
        SwingUtilities.convertPointToScreen(centerOnScreen, this);
        ignoreWarpedMouseEvent = true;
        mouseLookRobot.mouseMove(centerOnScreen.x, centerOnScreen.y);
    }

    private void updateSelectionTarget() {
        if (getWidth() <= 0 || getHeight() <= 0 || paused || respawnCountdown > 0) {
            selectedTarget = null;
            return;
        }

        if (viewMode == ViewMode.SUPERIOR) {
            updateTopSelectionTarget();
        } else {
            updateFirstPersonSelectionTarget();
        }
    }

    private void updateTopSelectionTarget() {
        selectedTarget = null;
        List<CellProjection> cells =
            isometricWorldRenderer.buildVisibleCells(world, player, cameraYaw, VIEW_RADIUS, getWidth(), getHeight());
        for (int index = cells.size() - 1; index >= 0; index -= 1) {
            CellProjection cell = cells.get(index);
            if (!cell.topVisible() || cell.topFace() == null || !cell.topFace().contains(mousePoint)) {
                continue;
            }

            boolean inReach = isCellInReach(cell.x(), cell.y(), cell.z());
            selectedTarget = new SelectionTarget(
                cell.x(),
                cell.y(),
                cell.z(),
                cell.x(),
                cell.y() + 1,
                cell.z(),
                inReach,
                cell.topFace(),
                0
            );
            return;
        }
    }

    private void updateFirstPersonSelectionTarget() {
        selectedTarget = firstPersonWorldRenderer.raycastSelection(world, player, cameraYaw, cameraPitch, INTERACT_RANGE);
    }

    private boolean isCellInReach(int x, int y, int z) {
        double centerX = x + 0.5;
        double centerY = y + 0.5;
        double centerZ = z + 0.5;
        double dx = centerX - player.x;
        double dy = centerY - (player.y + PLAYER_HEIGHT * 0.5);
        double dz = centerZ - player.z;
        return dx * dx + dy * dy + dz * dz <= INTERACT_RANGE * INTERACT_RANGE;
    }

    private void tryMineSelectedCell() {
        if (paused || respawnCountdown > 0) {
            return;
        }
        if (selectedTarget == null) {
            notice = "Nessun blocco selezionato.";
            return;
        }
        if (!selectedTarget.inReach()) {
            notice = "Blocco troppo lontano.";
            return;
        }

        if (world.removeBlock(selectedTarget.blockX(), selectedTarget.blockY(), selectedTarget.blockZ())) {
            notice = "Blocco rimosso.";
            updateSelectionTarget();
            repaint();
            return;
        }

        notice = "Questo blocco non puo essere rimosso.";
    }

    private void tryPlaceSelectedCell() {
        if (paused || respawnCountdown > 0) {
            return;
        }
        if (selectedTarget == null) {
            notice = "Nessun blocco selezionato.";
            return;
        }
        if (!selectedTarget.inReach()) {
            notice = "Blocco troppo lontano.";
            return;
        }

        int placeX = selectedTarget.placeX();
        int placeY = selectedTarget.placeY();
        int placeZ = selectedTarget.placeZ();
        if (wouldTrapPlayer(placeX, placeY, placeZ)) {
            notice = "Non puoi piazzare un blocco dentro al player.";
            return;
        }

        BlockType selectedBlock = hotbarBlocks[activeBlockIndex];
        if (world.placeBlock(placeX, placeY, placeZ, selectedBlock)) {
            notice = "Piazzato: " + selectedBlock.label() + ".";
            updateSelectionTarget();
            repaint();
            return;
        }

        notice = "Posizione occupata o fuori dal mondo.";
    }

    private boolean wouldTrapPlayer(int x, int y, int z) {
        double playerMinY = player.y + COLLISION_EPSILON;
        double playerMaxY = player.y + PLAYER_HEIGHT - COLLISION_EPSILON;
        return verticalOverlapsBlock(playerMinY, playerMaxY, y) && circleOverlapsBlockXZ(player.x, player.z, x, z);
    }

    private void selectHotbarSlot(int index) {
        if (index < 0 || index >= hotbarBlocks.length) {
            return;
        }
        activeBlockIndex = index;
        notice = "Blocco selezionato: " + hotbarBlocks[index].label() + ".";
    }

    private void drawSky(Graphics2D g2) {
        GradientPaint gradient = new GradientPaint(
            0,
            0,
            new Color(213, 237, 255),
            0,
            getHeight(),
            new Color(103, 162, 234)
        );
        g2.setPaint(gradient);
        g2.fillRect(0, 0, getWidth(), getHeight());
    }

    private void drawHud(Graphics2D g2) {
        int panelWidth = 590;
        int panelHeight = 178;

        g2.setColor(new Color(11, 18, 31, 190));
        g2.fillRoundRect(24, 22, panelWidth, panelHeight, 26, 26);
        g2.setColor(new Color(255, 255, 255, 34));
        g2.drawRoundRect(24, 22, panelWidth, panelHeight, 26, 26);

        g2.setColor(Color.WHITE);
        g2.setFont(getFont().deriveFont(Font.BOLD, 24f));
        g2.drawString("Blockforge Java", 42, 56);

        String modeLabel = viewMode == ViewMode.SUPERIOR ? "Superiore" : "Prima persona";
        String targetSummary = "Mira: -";
        if (selectedTarget != null) {
            targetSummary = "Mira: %d,%d,%d %s".formatted(
                selectedTarget.blockX(),
                selectedTarget.blockY(),
                selectedTarget.blockZ(),
                selectedTarget.inReach() ? "in portata" : "fuori portata"
            );
        }

        g2.setFont(getFont().deriveFont(Font.PLAIN, 15f));
        g2.setColor(new Color(232, 238, 250));
        g2.drawString("Vista: " + modeLabel, 42, 82);
        g2.drawString("Morti: " + deathCount, 210, 82);
        g2.drawString("Posizione: %.1f, %.1f, %.1f".formatted(player.x, player.y, player.z), 42, 104);
        g2.drawString("Rotazione: %.0f deg".formatted(Math.toDegrees(normalizeAngle(cameraYaw))), 42, 126);
        g2.drawString("Blocco: " + hotbarBlocks[activeBlockIndex].label(), 42, 148);
        g2.drawString(targetSummary, 42, 170);

        String controlSummary = viewMode == ViewMode.SUPERIOR
            ? "V cambia vista, Q/E ruota, click sx rimuove, dx piazza"
            : "V cambia vista, mouse o frecce su/giu guarda, click sx/dx interagisci";
        g2.drawString(controlSummary, 42, 192);

        g2.setColor(new Color(255, 240, 205));
        g2.drawString(notice, 42, getHeight() - 28);

        drawHotbar(g2);

        if (respawnCountdown > 0) {
            g2.setColor(new Color(10, 14, 24, 150));
            g2.fillRoundRect(getWidth() / 2 - 210, getHeight() / 2 - 64, 420, 128, 28, 28);
            g2.setColor(new Color(255, 245, 224));
            g2.setFont(getFont().deriveFont(Font.BOLD, 28f));
            g2.drawString("Sei morto", getWidth() / 2 - 70, getHeight() / 2 - 6);
            g2.setFont(getFont().deriveFont(Font.PLAIN, 18f));
            g2.drawString("Respawn tra %.1f s".formatted(respawnCountdown), getWidth() / 2 - 74, getHeight() / 2 + 28);
        }

        if (paused) {
            drawPauseMenu(g2);
        }
    }

    private void drawPauseMenu(Graphics2D g2) {
        g2.setColor(new Color(4, 8, 14, 188));
        g2.fillRect(0, 0, getWidth(), getHeight());

        int menuWidth = 560;
        int menuHeight = 506;
        int x = (getWidth() - menuWidth) / 2;
        int y = (getHeight() - menuHeight) / 2;

        g2.setPaint(new LinearGradientPaint(
            x,
            y,
            x + menuWidth,
            y + menuHeight,
            new float[] {0f, 0.55f, 1f},
            new Color[] {
                new Color(22, 33, 52, 244),
                new Color(10, 18, 32, 244),
                new Color(35, 23, 18, 244)
            }
        ));
        g2.fillRoundRect(x, y, menuWidth, menuHeight, 30, 30);
        g2.setColor(new Color(255, 214, 142, 85));
        g2.drawRoundRect(x, y, menuWidth, menuHeight, 30, 30);

        g2.setColor(new Color(255, 184, 77, 28));
        g2.fillOval(x + menuWidth - 180, y - 54, 220, 220);
        g2.setColor(new Color(120, 196, 255, 24));
        g2.fillOval(x - 72, y + menuHeight - 128, 210, 210);

        g2.setColor(new Color(255, 184, 77));
        g2.setFont(getFont().deriveFont(Font.BOLD, 13f));
        g2.drawString("BLOCKFORGE", x + 42, y + 46);
        g2.setColor(Color.WHITE);
        g2.setFont(getFont().deriveFont(Font.BOLD, 46f));
        g2.drawString("In pausa", x + 40, y + 92);

        g2.setFont(getFont().deriveFont(Font.PLAIN, 16f));
        g2.setColor(new Color(218, 228, 242));
        g2.drawString("Il mondo e fermo. Mouse-look, mira e movimento sono disattivati.", x + 42, y + 124);

        drawPauseButton(g2, PauseAction.RESUME, "Riprendi", "Esc / P", "Torna subito in gioco");
        drawPauseButton(g2, PauseAction.SAVE, "Salva partita", "S / F6", "Scrive lo stato corrente su disco");
        drawPauseButton(g2, PauseAction.LOAD, "Carica", "L / F9", "Ripristina l'ultimo salvataggio");
        drawPauseButton(
            g2,
            PauseAction.TOGGLE_AUTO_STEP,
            "Auto-step: " + (autoStepEnabled ? "ON" : "OFF"),
            "T",
            autoStepEnabled ? "Sali automaticamente sui blocchi" : "Richiede salto/manualita sui dislivelli"
        );

        g2.setColor(new Color(255, 240, 205, 215));
        g2.setFont(getFont().deriveFont(Font.PLAIN, 13f));
        g2.drawString("Salvataggio: " + savePath, x + 42, y + menuHeight - 44);
    }

    private void drawPauseButton(Graphics2D g2, PauseAction action, String label, String shortcut, String description) {
        Rectangle bounds = pauseButtonBounds(action);
        boolean hovered = action == hoveredPauseAction;

        g2.setPaint(new LinearGradientPaint(
            bounds.x,
            bounds.y,
            bounds.x + bounds.width,
            bounds.y + bounds.height,
            new float[] {0f, 1f},
            hovered
                ? new Color[] {new Color(255, 198, 104), new Color(255, 139, 75)}
                : new Color[] {new Color(35, 50, 73, 232), new Color(19, 30, 48, 232)}
        ));
        g2.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height, 22, 22);
        g2.setColor(hovered ? new Color(255, 248, 226) : new Color(255, 255, 255, 50));
        g2.drawRoundRect(bounds.x, bounds.y, bounds.width, bounds.height, 22, 22);

        g2.setColor(hovered ? new Color(25, 34, 49) : Color.WHITE);
        g2.setFont(getFont().deriveFont(Font.BOLD, 21f));
        g2.drawString(label, bounds.x + 22, bounds.y + 34);

        g2.setFont(getFont().deriveFont(Font.BOLD, 13f));
        g2.drawString(shortcut, bounds.x + bounds.width - 88, bounds.y + 31);

        g2.setFont(getFont().deriveFont(Font.PLAIN, 13f));
        g2.setColor(hovered ? new Color(58, 45, 35) : new Color(204, 214, 230));
        g2.drawString(description, bounds.x + 22, bounds.y + 57);
    }

    private Rectangle pauseButtonBounds(PauseAction action) {
        int menuWidth = 560;
        int x = (getWidth() - menuWidth) / 2 + 42;
        int y = (getHeight() - 506) / 2 + 158 + action.ordinal() * 76;
        return new Rectangle(x, y, menuWidth - 84, 62);
    }

    private PauseAction pauseActionAt(Point point) {
        for (PauseAction action : PauseAction.values()) {
            if (pauseButtonBounds(action).contains(point)) {
                return action;
            }
        }
        return null;
    }

    private void handlePauseMenuClick(Point point) {
        PauseAction action = pauseActionAt(point);
        if (action == null) {
            return;
        }

        switch (action) {
            case RESUME -> setPaused(false);
            case SAVE -> saveCurrentGame();
            case LOAD -> loadSavedGame();
            case TOGGLE_AUTO_STEP -> toggleAutoStep();
        }
    }

    private void toggleAutoStep() {
        autoStepEnabled = !autoStepEnabled;
        notice = autoStepEnabled
            ? "Auto-step attivo."
            : "Auto-step disattivato. Usa il salto per i dislivelli.";
        repaint();
    }

    private void setPaused(boolean paused) {
        this.paused = paused;
        pressedKeys.clear();
        jumpQueued = false;
        selectedTarget = null;
        hoveredPauseAction = null;
        mousePoint.setLocation(-10_000, -10_000);
        if (paused) {
            setFirstPersonMouseCapture(false);
            notice = "Gioco in pausa. Usa i pulsanti, S/L o Esc.";
        } else {
            lastFrameNanos = System.nanoTime();
            if (viewMode == ViewMode.FIRST_PERSON) {
                setFirstPersonMouseCapture(true);
            }
            notice = "Ripresa.";
            updateSelectionTarget();
        }
        repaint();
    }

    private void saveCurrentGame() {
        try {
            SaveGame.save(savePath, world, player, cameraYaw, cameraPitch, activeBlockIndex, deathCount, viewMode, autoStepEnabled);
            notice = "Partita salvata.";
        } catch (IOException exception) {
            notice = "Salvataggio fallito: " + exception.getMessage();
        }
        repaint();
    }

    private void loadSavedGame() {
        if (!Files.exists(savePath)) {
            notice = "Nessun salvataggio trovato.";
            repaint();
            return;
        }

        try {
            SaveGame.LoadedGame loadedGame = SaveGame.load(savePath);
            world = loadedGame.world();
            player.x = loadedGame.player().x;
            player.y = loadedGame.player().y;
            player.z = loadedGame.player().z;
            player.verticalVelocity = loadedGame.player().verticalVelocity;
            player.onGround = loadedGame.player().onGround;
            cameraYaw = loadedGame.cameraYaw();
            cameraPitch = loadedGame.cameraPitch();
            activeBlockIndex = Math.max(0, Math.min(hotbarBlocks.length - 1, loadedGame.activeBlockIndex()));
            deathCount = loadedGame.deathCount();
            viewMode = loadedGame.viewMode();
            autoStepEnabled = loadedGame.autoStepEnabled();
            respawnCountdown = 0;
            pressedKeys.clear();
            jumpQueued = false;
            setFirstPersonMouseCapture(!paused && viewMode == ViewMode.FIRST_PERSON);
            updateSelectionTarget();
            notice = "Salvataggio caricato.";
        } catch (IOException | IllegalArgumentException exception) {
            notice = "Caricamento fallito: " + exception.getMessage();
        }
        repaint();
    }

    private void drawHotbar(Graphics2D g2) {
        int slotWidth = 108;
        int slotHeight = 46;
        int gap = 10;
        int totalWidth = hotbarBlocks.length * slotWidth + (hotbarBlocks.length - 1) * gap;
        int startX = (getWidth() - totalWidth) / 2;
        int y = getHeight() - 96;

        for (int index = 0; index < hotbarBlocks.length; index += 1) {
            BlockType blockType = hotbarBlocks[index];
            int x = startX + index * (slotWidth + gap);
            boolean active = index == activeBlockIndex;

            g2.setColor(active ? new Color(255, 188, 95, 230) : new Color(11, 18, 31, 185));
            g2.fillRoundRect(x, y, slotWidth, slotHeight, 18, 18);
            g2.setColor(active ? new Color(255, 244, 220) : new Color(255, 255, 255, 34));
            g2.drawRoundRect(x, y, slotWidth, slotHeight, 18, 18);

            g2.setColor(blockType.topColor());
            g2.fillRoundRect(x + 10, y + 12, 18, 18, 6, 6);

            g2.setFont(getFont().deriveFont(active ? Font.BOLD : Font.PLAIN, 14f));
            g2.setColor(active ? new Color(25, 34, 49) : Color.WHITE);
            g2.drawString((index + 1) + " " + blockType.label(), x + 36, y + 27);
        }
    }

    private boolean canOccupy(double centerX, double feetY, double centerZ) {
        double bodyMinY = feetY + COLLISION_EPSILON;
        double bodyMaxY = feetY + PLAYER_HEIGHT - COLLISION_EPSILON;

        if (bodyMaxY < world.minBlockY() || bodyMinY > world.maxBlockY() + 1.0) {
            return true;
        }

        int startX = (int) Math.floor(centerX - PLAYER_RADIUS);
        int endX = (int) Math.floor(centerX + PLAYER_RADIUS);
        int startY = Math.max(world.minBlockY(), (int) Math.floor(bodyMinY));
        int endY = Math.min(world.maxBlockY(), (int) Math.floor(bodyMaxY));
        int startZ = (int) Math.floor(centerZ - PLAYER_RADIUS);
        int endZ = (int) Math.floor(centerZ + PLAYER_RADIUS);

        for (int blockX = startX; blockX <= endX; blockX += 1) {
            for (int blockY = startY; blockY <= endY; blockY += 1) {
                for (int blockZ = startZ; blockZ <= endZ; blockZ += 1) {
                    if (!world.hasBlock(blockX, blockY, blockZ)) {
                        continue;
                    }
                    if (
                        verticalOverlapsBlock(bodyMinY, bodyMaxY, blockY) &&
                            circleOverlapsBlockXZ(centerX, centerZ, blockX, blockZ)
                    ) {
                        return false;
                    }
                }
            }
        }

        return true;
    }

    private boolean verticalOverlapsBlock(double minY, double maxY, int blockY) {
        return minY < blockY + 1.0 && maxY > blockY;
    }

    private boolean circleOverlapsBlockXZ(double centerX, double centerZ, int blockX, int blockZ) {
        double closestX = clamp(centerX, blockX, blockX + 1.0);
        double closestZ = clamp(centerZ, blockZ, blockZ + 1.0);
        double deltaX = centerX - closestX;
        double deltaZ = centerZ - closestZ;
        double effectiveRadius = PLAYER_RADIUS - COLLISION_EPSILON;
        return deltaX * deltaX + deltaZ * deltaZ < effectiveRadius * effectiveRadius;
    }

    private double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }

    private double normalizeAngle(double radians) {
        double normalized = radians % (Math.PI * 2);
        if (normalized < 0) {
            normalized += Math.PI * 2;
        }
        return normalized;
    }

    private Cursor createHiddenCursor() {
        BufferedImage image = new BufferedImage(16, 16, BufferedImage.TYPE_INT_ARGB);
        return Toolkit.getDefaultToolkit().createCustomCursor(image, new Point(0, 0), "blockforge-hidden");
    }

    private Robot createMouseLookRobot() {
        try {
            return new Robot();
        } catch (AWTException exception) {
            return null;
        }
    }

    private final class InputHandler extends KeyAdapter {
        @Override
        public void keyPressed(KeyEvent event) {
            if (event.getKeyCode() == KeyEvent.VK_ESCAPE || event.getKeyCode() == KeyEvent.VK_P) {
                setPaused(!paused);
                return;
            }
            if (event.getKeyCode() == KeyEvent.VK_F6) {
                saveCurrentGame();
                return;
            }
            if (event.getKeyCode() == KeyEvent.VK_F9) {
                loadSavedGame();
                return;
            }
            if (paused) {
                if (event.getKeyCode() == KeyEvent.VK_S) {
                    saveCurrentGame();
                } else if (event.getKeyCode() == KeyEvent.VK_L) {
                    loadSavedGame();
                } else if (event.getKeyCode() == KeyEvent.VK_T) {
                    toggleAutoStep();
                }
                return;
            }

            pressedKeys.add(event.getKeyCode());

            switch (event.getKeyCode()) {
                case KeyEvent.VK_SPACE -> jumpQueued = true;
                case KeyEvent.VK_R -> {
                    respawnPlayer();
                    notice = "Respawn manuale.";
                }
                case KeyEvent.VK_V, KeyEvent.VK_F5 -> toggleViewMode();
                case KeyEvent.VK_1 -> selectHotbarSlot(0);
                case KeyEvent.VK_2 -> selectHotbarSlot(1);
                case KeyEvent.VK_3 -> selectHotbarSlot(2);
                case KeyEvent.VK_4 -> selectHotbarSlot(3);
                case KeyEvent.VK_5 -> selectHotbarSlot(4);
                default -> {
                }
            }
        }

        @Override
        public void keyReleased(KeyEvent event) {
            pressedKeys.remove(event.getKeyCode());
        }
    }

    private enum PauseAction {
        RESUME,
        SAVE,
        LOAD,
        TOGGLE_AUTO_STEP
    }

    private record HorizontalPush(double x, double z) {
    }
}
