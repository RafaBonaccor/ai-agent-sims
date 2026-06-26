package blockforge;

import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.Polygon;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

final class FirstPersonWorldRenderer {
    private static final double FIRST_PERSON_EYE_HEIGHT = 1.55;
    private static final double FIRST_PERSON_FOV = Math.toRadians(72);
    private static final double FIRST_PERSON_MAX_DISTANCE = 42.0;
    private static final double FIRST_PERSON_MAX_DISTANCE_SQUARED = FIRST_PERSON_MAX_DISTANCE * FIRST_PERSON_MAX_DISTANCE;
    private static final double FIRST_PERSON_NEAR_PLANE = 0.08;
    private static final double VOID_FLOOR_Y = -7.0;
    private static final int FIRST_PERSON_VIEW_RADIUS = 14;
    private static final double FACE_CULL_DOT_THRESHOLD = Math.cos(FIRST_PERSON_FOV * 0.62);

    private final Map<Long, GreedyMesher.ChunkMesh> chunkMeshCache = new HashMap<>();
    private World cachedWorld;

    void drawWorld(Graphics2D g2, World world, Player player, double cameraYaw, double cameraPitch, int panelWidth, int panelHeight) {
        List<FaceRender> faces = new ArrayList<>();
        double eyeY = player.y + FIRST_PERSON_EYE_HEIGHT;
        int centerCellX = (int) Math.floor(player.x);
        int centerCellZ = (int) Math.floor(player.z);
        int minViewX = centerCellX - FIRST_PERSON_VIEW_RADIUS;
        int maxViewX = centerCellX + FIRST_PERSON_VIEW_RADIUS;
        int minViewZ = centerCellZ - FIRST_PERSON_VIEW_RADIUS;
        int maxViewZ = centerCellZ + FIRST_PERSON_VIEW_RADIUS;

        if (cachedWorld != world) {
            chunkMeshCache.clear();
            cachedWorld = world;
        }

        for (World.WorldChunk chunk : world.chunksNear(player.x, player.z, FIRST_PERSON_VIEW_RADIUS)) {
            if (!isChunkInsideCameraCone(world, chunk, player, cameraYaw)) {
                continue;
            }

            for (int x = chunk.minX(); x <= chunk.maxX(); x += 1) {
                for (int z = chunk.minZ(); z <= chunk.maxZ(); z += 1) {
                    if (!isInsideSquareView(x, z, minViewX, maxViewX, minViewZ, maxViewZ)) {
                        continue;
                    }

                    if (world.isVoidCell(x, z)) {
                        addVoidFloorFace(faces, player, cameraYaw, cameraPitch, panelWidth, panelHeight, x, z);
                    }
                }
            }

            addCachedChunkMeshFaces(
                faces,
                world,
                chunk,
                player,
                cameraYaw,
                cameraPitch,
                panelWidth,
                panelHeight,
                eyeY
            );
        }

        faces.sort(Comparator.comparingDouble(FaceRender::depth).reversed());
        for (FaceRender face : faces) {
            g2.setColor(face.color());
            g2.fillPolygon(face.polygon());
            g2.setColor(new Color(255, 255, 255, 18));
            g2.drawPolygon(face.polygon());
        }
    }

    private void addCachedChunkMeshFaces(
        List<FaceRender> faces,
        World world,
        World.WorldChunk chunk,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        double eyeY
    ) {
        GreedyMesher.ChunkMesh chunkMesh = cachedChunkMesh(world, chunk);
        for (GreedyMesher.MeshFace meshFace : chunkMesh.faces()) {
            addMeshFace(faces, world, player, cameraYaw, cameraPitch, panelWidth, panelHeight, eyeY, meshFace);
        }
    }

    private GreedyMesher.ChunkMesh cachedChunkMesh(World world, World.WorldChunk chunk) {
        long key = chunkKey(chunk);
        GreedyMesher.ChunkMesh chunkMesh = chunkMeshCache.get(key);
        if (chunkMesh == null || chunkMesh.revision() != world.chunkRevision(chunk)) {
            chunkMesh = GreedyMesher.buildChunkMesh(world, chunk);
            chunkMeshCache.put(key, chunkMesh);
        }
        return chunkMesh;
    }

    private long chunkKey(World.WorldChunk chunk) {
        return ((long) chunk.chunkX() << 32) ^ (chunk.chunkZ() & 0xffff_ffffL);
    }

    private void addMeshFace(
        List<FaceRender> faces,
        World world,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        double eyeY,
        GreedyMesher.MeshFace meshFace
    ) {
        if (!isMeshFaceNearAndInFront(player, cameraYaw, meshFace)) {
            return;
        }

        switch (meshFace.orientation()) {
            case TOP -> addTopMeshFace(faces, world, player, cameraYaw, cameraPitch, panelWidth, panelHeight, eyeY, meshFace);
            case BOTTOM -> addBottomMeshFace(faces, player, cameraYaw, cameraPitch, panelWidth, panelHeight, eyeY, meshFace);
            case EAST, WEST, SOUTH, NORTH -> addSideMeshFace(faces, player, cameraYaw, cameraPitch, panelWidth, panelHeight, meshFace);
        }
    }

    private boolean isMeshFaceNearAndInFront(Player player, double cameraYaw, GreedyMesher.MeshFace meshFace) {
        Vec3 center = meshFaceCenter(meshFace);
        double dx = center.x() - player.x;
        double dy = center.y() - (player.y + FIRST_PERSON_EYE_HEIGHT);
        double dz = center.z() - player.z;
        double distanceSquared = dx * dx + dy * dy + dz * dz;
        if (distanceSquared > FIRST_PERSON_MAX_DISTANCE_SQUARED) {
            return false;
        }

        double horizontalDistance = Math.hypot(dx, dz);
        if (horizontalDistance < worldFaceDiagonalMargin(meshFace)) {
            return true;
        }

        double forwardX = Math.cos(cameraYaw);
        double forwardZ = Math.sin(cameraYaw);
        double dot = (dx * forwardX + dz * forwardZ) / horizontalDistance;
        double angularMargin = Math.min(0.45, worldFaceDiagonalMargin(meshFace) / horizontalDistance);
        return dot >= FACE_CULL_DOT_THRESHOLD - angularMargin;
    }

    private Vec3 meshFaceCenter(GreedyMesher.MeshFace meshFace) {
        return switch (meshFace.orientation()) {
            case TOP -> new Vec3(
                meshFace.x() + meshFace.width() * 0.5,
                meshFace.y() + 1.0,
                meshFace.z() + meshFace.height() * 0.5
            );
            case BOTTOM -> new Vec3(
                meshFace.x() + meshFace.width() * 0.5,
                meshFace.y(),
                meshFace.z() + meshFace.height() * 0.5
            );
            case EAST, WEST, SOUTH, NORTH -> sideFaceCenter(meshFace);
        };
    }

    private double worldFaceDiagonalMargin(GreedyMesher.MeshFace meshFace) {
        double a = Math.max(1, meshFace.width());
        double b = Math.max(1, meshFace.height());
        return Math.sqrt(a * a + b * b) * 0.5 + 1.25;
    }

    private void addTopMeshFace(
        List<FaceRender> faces,
        World world,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        double eyeY,
        GreedyMesher.MeshFace meshFace
    ) {
        if (eyeY < meshFace.y() + 0.95) {
            return;
        }

        int maxX = meshFace.x() + meshFace.width();
        int maxZ = meshFace.z() + meshFace.height();
        double y = meshFace.y() + 1.0;
        addFace(
            faces,
            player,
            cameraYaw,
            cameraPitch,
            panelWidth,
            panelHeight,
            new Vec3(meshFace.x(), y, meshFace.z()),
            new Vec3(maxX, y, meshFace.z()),
            new Vec3(maxX, y, maxZ),
            new Vec3(meshFace.x(), y, maxZ),
            meshFace.color(),
            meshFace.x() + meshFace.width() * 0.5,
            y,
            meshFace.z() + meshFace.height() * 0.5
        );
    }

    private void addBottomMeshFace(
        List<FaceRender> faces,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        double eyeY,
        GreedyMesher.MeshFace meshFace
    ) {
        if (eyeY > meshFace.y() + 0.05) {
            return;
        }

        int maxX = meshFace.x() + meshFace.width();
        int maxZ = meshFace.z() + meshFace.height();
        addFace(
            faces,
            player,
            cameraYaw,
            cameraPitch,
            panelWidth,
            panelHeight,
            new Vec3(meshFace.x(), meshFace.y(), maxZ),
            new Vec3(maxX, meshFace.y(), maxZ),
            new Vec3(maxX, meshFace.y(), meshFace.z()),
            new Vec3(meshFace.x(), meshFace.y(), meshFace.z()),
            meshFace.color(),
            meshFace.x() + meshFace.width() * 0.5,
            meshFace.y(),
            meshFace.z() + meshFace.height() * 0.5
        );
    }

    private void addSideMeshFace(
        List<FaceRender> faces,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        GreedyMesher.MeshFace meshFace
    ) {
        if (!isSideFacingPlayer(player, meshFace)) {
            return;
        }

        Vec3[] corners = sideFaceCorners(meshFace);
        Vec3 center = sideFaceCenter(meshFace);
        addFace(
            faces,
            player,
            cameraYaw,
            cameraPitch,
            panelWidth,
            panelHeight,
            corners[0],
            corners[1],
            corners[2],
            corners[3],
            meshFace.color(),
            center.x(),
            center.y(),
            center.z()
        );
    }

    private boolean isSideFacingPlayer(Player player, GreedyMesher.MeshFace meshFace) {
        Vec3 normal = faceNormal(meshFace.orientation());
        Vec3 center = sideFaceCenter(meshFace);
        double toEyeX = player.x - center.x();
        double toEyeY = player.y + FIRST_PERSON_EYE_HEIGHT - center.y();
        double toEyeZ = player.z - center.z();
        return normal.x() * toEyeX + normal.y() * toEyeY + normal.z() * toEyeZ > 0;
    }

    private Vec3[] sideFaceCorners(GreedyMesher.MeshFace meshFace) {
        int x = meshFace.x();
        int y = meshFace.y();
        int z = meshFace.z();
        int maxA = x + meshFace.width();
        int maxB = z + meshFace.width();
        int maxY = y + meshFace.height();

        return switch (meshFace.orientation()) {
            case EAST -> new Vec3[] {
                new Vec3(x + 1, maxY, z),
                new Vec3(x + 1, maxY, maxB),
                new Vec3(x + 1, y, maxB),
                new Vec3(x + 1, y, z)
            };
            case WEST -> new Vec3[] {
                new Vec3(x, maxY, maxB),
                new Vec3(x, maxY, z),
                new Vec3(x, y, z),
                new Vec3(x, y, maxB)
            };
            case SOUTH -> new Vec3[] {
                new Vec3(maxA, maxY, z + 1),
                new Vec3(x, maxY, z + 1),
                new Vec3(x, y, z + 1),
                new Vec3(maxA, y, z + 1)
            };
            case NORTH -> new Vec3[] {
                new Vec3(x, maxY, z),
                new Vec3(maxA, maxY, z),
                new Vec3(maxA, y, z),
                new Vec3(x, y, z)
            };
            default -> throw new IllegalArgumentException("Not a side face: " + meshFace.orientation());
        };
    }

    private Vec3 sideFaceCenter(GreedyMesher.MeshFace meshFace) {
        return switch (meshFace.orientation()) {
            case EAST -> new Vec3(meshFace.x() + 1.0, meshFace.y() + meshFace.height() * 0.5, meshFace.z() + meshFace.width() * 0.5);
            case WEST -> new Vec3(meshFace.x(), meshFace.y() + meshFace.height() * 0.5, meshFace.z() + meshFace.width() * 0.5);
            case SOUTH -> new Vec3(meshFace.x() + meshFace.width() * 0.5, meshFace.y() + meshFace.height() * 0.5, meshFace.z() + 1.0);
            case NORTH -> new Vec3(meshFace.x() + meshFace.width() * 0.5, meshFace.y() + meshFace.height() * 0.5, meshFace.z());
            default -> throw new IllegalArgumentException("Not a side face: " + meshFace.orientation());
        };
    }

    private Vec3 faceNormal(GreedyMesher.Orientation orientation) {
        return switch (orientation) {
            case EAST -> new Vec3(1, 0, 0);
            case WEST -> new Vec3(-1, 0, 0);
            case SOUTH -> new Vec3(0, 0, 1);
            case NORTH -> new Vec3(0, 0, -1);
            case TOP -> new Vec3(0, 1, 0);
            case BOTTOM -> new Vec3(0, -1, 0);
        };
    }

    private boolean isInsideSquareView(int x, int z, int minViewX, int maxViewX, int minViewZ, int maxViewZ) {
        return x >= minViewX && x <= maxViewX && z >= minViewZ && z <= maxViewZ;
    }

    private boolean isChunkInsideCameraCone(World world, World.WorldChunk chunk, Player player, double cameraYaw) {
        double dx = chunk.centerX() - player.x;
        double dz = chunk.centerZ() - player.z;
        double distance = Math.hypot(dx, dz);
        if (distance < worldChunkDiagonalMargin(world)) {
            return true;
        }

        double forwardX = Math.cos(cameraYaw);
        double forwardZ = Math.sin(cameraYaw);
        double dot = (dx * forwardX + dz * forwardZ) / distance;
        double chunkAngularMargin = Math.min(0.85, worldChunkDiagonalMargin(world) / distance);
        double minVisibleDot = Math.cos(FIRST_PERSON_FOV * 0.72) - chunkAngularMargin;
        return dot >= minVisibleDot;
    }

    private double worldChunkDiagonalMargin(World world) {
        return Math.sqrt(world.chunkSize() * world.chunkSize() * 2.0) * 0.5 + 2.0;
    }

    void drawCrosshair(Graphics2D g2, int panelWidth, int panelHeight) {
        int centerX = panelWidth / 2;
        int centerY = panelHeight / 2;
        g2.setStroke(new BasicStroke(2f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
        g2.setColor(new Color(255, 255, 255, 220));
        g2.drawLine(centerX - 10, centerY, centerX + 10, centerY);
        g2.drawLine(centerX, centerY - 10, centerX, centerY + 10);
    }

    SelectionTarget raycastSelection(World world, Player player, double cameraYaw, double cameraPitch, double interactRange) {
        double eyeX = player.x;
        double eyeY = player.y + FIRST_PERSON_EYE_HEIGHT;
        double eyeZ = player.z;
        double cosPitch = Math.cos(cameraPitch);
        double dirX = Math.cos(cameraYaw) * cosPitch;
        double dirY = Math.sin(cameraPitch);
        double dirZ = Math.sin(cameraYaw) * cosPitch;

        int lastEmptyX = Integer.MIN_VALUE;
        int lastEmptyY = Integer.MIN_VALUE;
        int lastEmptyZ = Integer.MIN_VALUE;

        for (double distance = 0.15; distance <= interactRange; distance += 0.03) {
            double sampleX = eyeX + dirX * distance;
            double sampleY = eyeY + dirY * distance;
            double sampleZ = eyeZ + dirZ * distance;

            int blockX = (int) Math.floor(sampleX);
            int blockY = (int) Math.floor(sampleY);
            int blockZ = (int) Math.floor(sampleZ);

            if (!world.containsBlockPosition(blockX, blockY, blockZ)) {
                continue;
            }

            if (world.hasBlock(blockX, blockY, blockZ)) {
                int placeX = lastEmptyX == Integer.MIN_VALUE ? blockX : lastEmptyX;
                int placeY = lastEmptyY == Integer.MIN_VALUE ? blockY + 1 : lastEmptyY;
                int placeZ = lastEmptyZ == Integer.MIN_VALUE ? blockZ : lastEmptyZ;
                return new SelectionTarget(blockX, blockY, blockZ, placeX, placeY, placeZ, true, null, distance);
            }

            lastEmptyX = blockX;
            lastEmptyY = blockY;
            lastEmptyZ = blockZ;
        }

        return null;
    }

    private void addVoidFloorFace(
        List<FaceRender> faces,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        int x,
        int z
    ) {
        addFace(
            faces,
            player,
            cameraYaw,
            cameraPitch,
            panelWidth,
            panelHeight,
            new Vec3(x, VOID_FLOOR_Y, z),
            new Vec3(x + 1, VOID_FLOOR_Y, z),
            new Vec3(x + 1, VOID_FLOOR_Y, z + 1),
            new Vec3(x, VOID_FLOOR_Y, z + 1),
            new Color(16, 20, 33),
            x + 0.5,
            VOID_FLOOR_Y,
            z + 0.5
        );
    }

    private void addFace(
        List<FaceRender> faces,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        Vec3 p1,
        Vec3 p2,
        Vec3 p3,
        Vec3 p4,
        Color baseColor,
        double centerX,
        double centerY,
        double centerZ
    ) {
        List<CameraPoint> clippedPoints = clipToNearPlane(
            List.of(
                toCameraPoint(player, cameraYaw, cameraPitch, p1.x(), p1.y(), p1.z()),
                toCameraPoint(player, cameraYaw, cameraPitch, p2.x(), p2.y(), p2.z()),
                toCameraPoint(player, cameraYaw, cameraPitch, p3.x(), p3.y(), p3.z()),
                toCameraPoint(player, cameraYaw, cameraPitch, p4.x(), p4.y(), p4.z())
            )
        );
        if (clippedPoints.size() < 3) {
            return;
        }

        int[] xs = new int[clippedPoints.size()];
        int[] ys = new int[clippedPoints.size()];
        double depthSum = 0;
        for (int index = 0; index < clippedPoints.size(); index += 1) {
            CameraPoint clippedPoint = clippedPoints.get(index);
            ScreenPoint screenPoint = projectCameraPoint(clippedPoint, panelWidth, panelHeight);
            xs[index] = (int) Math.round(screenPoint.screenX());
            ys[index] = (int) Math.round(screenPoint.screenY());
            depthSum += clippedPoint.z();
        }

        Polygon polygon = new Polygon(xs, ys, clippedPoints.size());

        if (polygon.getBounds().width <= 0 || polygon.getBounds().height <= 0) {
            return;
        }

        double faceDepth = depthSum / clippedPoints.size();
        if (faceDepth > FIRST_PERSON_MAX_DISTANCE) {
            return;
        }

        faces.add(new FaceRender(polygon, applyDistanceFog(baseColor, faceDepth, false), faceDepth));
    }

    private List<CameraPoint> clipToNearPlane(List<CameraPoint> polygon) {
        List<CameraPoint> clipped = new ArrayList<>();
        CameraPoint previousPoint = polygon.get(polygon.size() - 1);
        boolean previousInside = previousPoint.z() >= FIRST_PERSON_NEAR_PLANE;

        for (CameraPoint currentPoint : polygon) {
            boolean currentInside = currentPoint.z() >= FIRST_PERSON_NEAR_PLANE;
            if (currentInside != previousInside) {
                clipped.add(intersectNearPlane(previousPoint, currentPoint));
            }
            if (currentInside) {
                clipped.add(currentPoint);
            }
            previousPoint = currentPoint;
            previousInside = currentInside;
        }

        return clipped;
    }

    private CameraPoint intersectNearPlane(CameraPoint start, CameraPoint end) {
        double deltaZ = end.z() - start.z();
        if (Math.abs(deltaZ) < 1e-9) {
            return new CameraPoint(start.x(), start.y(), FIRST_PERSON_NEAR_PLANE);
        }

        double t = (FIRST_PERSON_NEAR_PLANE - start.z()) / deltaZ;
        return new CameraPoint(
            start.x() + (end.x() - start.x()) * t,
            start.y() + (end.y() - start.y()) * t,
            FIRST_PERSON_NEAR_PLANE
        );
    }

    private ScreenPoint projectCameraPoint(CameraPoint cameraPoint, int panelWidth, int panelHeight) {
        double focalLength = panelWidth * 0.5 / Math.tan(FIRST_PERSON_FOV * 0.5);
        double scale = focalLength / cameraPoint.z();
        double screenX = panelWidth * 0.5 + cameraPoint.x() * scale;
        double screenY = panelHeight * 0.5 - cameraPoint.y() * scale;
        return new ScreenPoint(screenX, screenY);
    }

    private CameraPoint toCameraPoint(
        Player player,
        double cameraYaw,
        double cameraPitch,
        double worldX,
        double worldY,
        double worldZ
    ) {
        double dx = worldX - player.x;
        double dy = worldY - (player.y + FIRST_PERSON_EYE_HEIGHT);
        double dz = worldZ - player.z;

        double forwardX = Math.cos(cameraYaw);
        double forwardZ = Math.sin(cameraYaw);
        double rightX = Math.sin(cameraYaw);
        double rightZ = -Math.cos(cameraYaw);

        double cameraX = dx * rightX + dz * rightZ;
        double cameraZ = dx * forwardX + dz * forwardZ;
        double cameraY = dy;

        double cosPitch = Math.cos(cameraPitch);
        double sinPitch = Math.sin(cameraPitch);
        double pitchedY = cameraY * cosPitch - cameraZ * sinPitch;
        double pitchedZ = cameraY * sinPitch + cameraZ * cosPitch;
        return new CameraPoint(cameraX, pitchedY, pitchedZ);
    }

    private ProjectedPoint projectFirstPerson(
        Player player,
        double cameraYaw,
        double cameraPitch,
        int panelWidth,
        int panelHeight,
        double worldX,
        double worldY,
        double worldZ
    ) {
        double dx = worldX - player.x;
        double dy = worldY - (player.y + FIRST_PERSON_EYE_HEIGHT);
        double dz = worldZ - player.z;

        double forwardX = Math.cos(cameraYaw);
        double forwardZ = Math.sin(cameraYaw);
        double rightX = Math.sin(cameraYaw);
        double rightZ = -Math.cos(cameraYaw);

        double cameraX = dx * rightX + dz * rightZ;
        double cameraZ = dx * forwardX + dz * forwardZ;
        double cameraY = dy;

        double cosPitch = Math.cos(cameraPitch);
        double sinPitch = Math.sin(cameraPitch);
        double pitchedY = cameraY * cosPitch - cameraZ * sinPitch;
        double pitchedZ = cameraY * sinPitch + cameraZ * cosPitch;

        if (pitchedZ <= FIRST_PERSON_NEAR_PLANE || pitchedZ > FIRST_PERSON_MAX_DISTANCE) {
            return null;
        }

        double focalLength = panelWidth * 0.5 / Math.tan(FIRST_PERSON_FOV * 0.5);
        double scale = focalLength / pitchedZ;
        double screenX = panelWidth * 0.5 + cameraX * scale;
        double screenY = panelHeight * 0.5 - pitchedY * scale;
        return new ProjectedPoint(screenX, screenY, pitchedZ);
    }

    private double depthFromCamera(
        Player player,
        double cameraYaw,
        double cameraPitch,
        double worldX,
        double worldY,
        double worldZ
    ) {
        double dx = worldX - player.x;
        double dy = worldY - (player.y + FIRST_PERSON_EYE_HEIGHT);
        double dz = worldZ - player.z;
        double forwardX = Math.cos(cameraYaw);
        double forwardZ = Math.sin(cameraYaw);
        return dx * forwardX + dz * forwardZ + dy * Math.sin(cameraPitch);
    }

    private Color applyDistanceFog(Color baseColor, double depth, boolean voidCell) {
        double fogAmount = clamp(depth / FIRST_PERSON_MAX_DISTANCE, 0, 1);
        Color fogColor = voidCell ? new Color(22, 27, 39) : new Color(164, 204, 244);
        int red = (int) Math.round(baseColor.getRed() * (1 - fogAmount) + fogColor.getRed() * fogAmount);
        int green = (int) Math.round(baseColor.getGreen() * (1 - fogAmount) + fogColor.getGreen() * fogAmount);
        int blue = (int) Math.round(baseColor.getBlue() * (1 - fogAmount) + fogColor.getBlue() * fogAmount);
        return new Color(red, green, blue);
    }

    private double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }

    private record Vec3(double x, double y, double z) {
    }

    private record CameraPoint(double x, double y, double z) {
    }

    private record ScreenPoint(double screenX, double screenY) {
    }

    private record ProjectedPoint(double screenX, double screenY, double depth) {
    }

    private record FaceRender(Polygon polygon, Color color, double depth) {
    }
}
