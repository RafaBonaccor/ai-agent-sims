package blockforge;

import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.Polygon;
import java.awt.geom.Point2D;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

final class IsometricWorldRenderer {
    private static final int TILE_WIDTH = 52;
    private static final int TILE_HEIGHT = 26;
    private static final int BLOCK_HEIGHT = 20;
    private static final int VOID_TILE_Y = -1;
    private static final double PLAYER_HEIGHT = 1.7;

    List<CellProjection> buildVisibleCells(
        World world,
        Player player,
        double cameraYaw,
        int viewRadius,
        int panelWidth,
        int panelHeight
    ) {
        List<CellProjection> blocks = new ArrayList<>();

        for (World.WorldChunk chunk : world.chunksNear(player.x, player.z, viewRadius)) {
            for (int x = chunk.minX(); x <= chunk.maxX(); x += 1) {
                for (int z = chunk.minZ(); z <= chunk.maxZ(); z += 1) {
                    if (!isInsideSquareView(player, x, z, viewRadius)) {
                        continue;
                    }

                    for (int y = world.minBlockY(); y <= world.maxBlockY(); y += 1) {
                        if (!world.hasBlock(x, y, z)) {
                            continue;
                        }

                        boolean topVisible = !world.hasBlock(x, y + 1, z);
                        boolean anyFaceVisible =
                            topVisible ||
                            !world.hasBlock(x + 1, y, z) ||
                            !world.hasBlock(x - 1, y, z) ||
                            !world.hasBlock(x, y, z + 1) ||
                            !world.hasBlock(x, y, z - 1);

                        if (!anyFaceVisible) {
                            continue;
                        }

                        Polygon topFace = topVisible
                            ? topFacePolygon(player, cameraYaw, panelWidth, panelHeight, x, y, z)
                            : null;
                        double depth = depthForBlock(player, cameraYaw, x + 0.5, y + 0.5, z + 0.5);
                        blocks.add(new CellProjection(x, y, z, depth, topFace, topVisible));
                    }
                }
            }
        }

        blocks.sort(Comparator.comparingDouble(CellProjection::depth));
        return blocks;
    }

    void drawWorld(
        Graphics2D g2,
        World world,
        Player player,
        double cameraYaw,
        int viewRadius,
        int panelWidth,
        int panelHeight
    ) {
        List<CellProjection> visibleBlocks = buildVisibleCells(world, player, cameraYaw, viewRadius, panelWidth, panelHeight);
        for (CellProjection block : visibleBlocks) {
            BlockType blockType = world.blockAt(block.x(), block.y(), block.z());
            if (blockType != null) {
                drawBlock(g2, world, player, cameraYaw, panelWidth, panelHeight, block.x(), block.y(), block.z(), blockType);
            }
        }

        drawVoidTiles(g2, world, player, cameraYaw, viewRadius, panelWidth, panelHeight);
    }

    void drawSelection(Graphics2D g2, SelectionTarget selectedTarget) {
        if (selectedTarget == null || selectedTarget.topFace() == null) {
            return;
        }

        Color fill = selectedTarget.inReach()
            ? new Color(255, 245, 220, 52)
            : new Color(255, 110, 110, 46);
        Color border = selectedTarget.inReach()
            ? new Color(255, 220, 140, 210)
            : new Color(255, 120, 120, 210);

        g2.setColor(fill);
        g2.fillPolygon(selectedTarget.topFace());
        g2.setStroke(new BasicStroke(2.5f));
        g2.setColor(border);
        g2.drawPolygon(selectedTarget.topFace());
    }

    void drawPlayer(Graphics2D g2, Player player, double cameraYaw, int panelWidth, int panelHeight) {
        Point2D.Double feet = project(player, cameraYaw, panelWidth, panelHeight, player.x, player.y, player.z);
        Point2D.Double head = project(player, cameraYaw, panelWidth, panelHeight, player.x, player.y + PLAYER_HEIGHT, player.z);

        g2.setStroke(new BasicStroke(4f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
        g2.setColor(new Color(235, 70, 70));
        g2.drawLine((int) feet.x, (int) feet.y, (int) head.x, (int) head.y);
        g2.fillOval((int) head.x - 8, (int) head.y - 8, 16, 16);
        g2.setColor(new Color(255, 255, 255, 90));
        g2.fillOval((int) feet.x - 10, (int) feet.y - 5, 20, 10);
    }

    private void drawVoidTiles(
        Graphics2D g2,
        World world,
        Player player,
        double cameraYaw,
        int viewRadius,
        int panelWidth,
        int panelHeight
    ) {
        for (World.WorldChunk chunk : world.chunksNear(player.x, player.z, viewRadius)) {
            for (int x = chunk.minX(); x <= chunk.maxX(); x += 1) {
                for (int z = chunk.minZ(); z <= chunk.maxZ(); z += 1) {
                    if (!isInsideSquareView(player, x, z, viewRadius) || !world.isVoidCell(x, z)) {
                        continue;
                    }
                    Polygon topFace = topFacePolygon(player, cameraYaw, panelWidth, panelHeight, x, VOID_TILE_Y, z);
                    g2.setColor(new Color(10, 14, 24, 170));
                    g2.fillPolygon(topFace);
                    g2.setColor(new Color(255, 184, 77, 90));
                    g2.drawPolygon(topFace);
                }
            }
        }
    }

    private boolean isInsideSquareView(Player player, int x, int z, int viewRadius) {
        int centerCellX = (int) Math.floor(player.x);
        int centerCellZ = (int) Math.floor(player.z);
        return x >= centerCellX - viewRadius &&
            x <= centerCellX + viewRadius &&
            z >= centerCellZ - viewRadius &&
            z <= centerCellZ + viewRadius;
    }

    private void drawBlock(
        Graphics2D g2,
        World world,
        Player player,
        double cameraYaw,
        int panelWidth,
        int panelHeight,
        int x,
        int y,
        int z,
        BlockType blockType
    ) {
        Point2D.Double topNw = project(player, cameraYaw, panelWidth, panelHeight, x, y + 1, z);
        Point2D.Double topNe = project(player, cameraYaw, panelWidth, panelHeight, x + 1, y + 1, z);
        Point2D.Double topSe = project(player, cameraYaw, panelWidth, panelHeight, x + 1, y + 1, z + 1);
        Point2D.Double topSw = project(player, cameraYaw, panelWidth, panelHeight, x, y + 1, z + 1);
        Point2D.Double baseNe = project(player, cameraYaw, panelWidth, panelHeight, x + 1, y, z);
        Point2D.Double baseSe = project(player, cameraYaw, panelWidth, panelHeight, x + 1, y, z + 1);
        Point2D.Double baseSw = project(player, cameraYaw, panelWidth, panelHeight, x, y, z + 1);
        Point2D.Double baseNw = project(player, cameraYaw, panelWidth, panelHeight, x, y, z);

        if (!world.hasBlock(x + 1, y, z)) {
            Polygon eastFace = polygon(topNe, topSe, baseSe, baseNe);
            g2.setColor(blockType.rightColor());
            g2.fillPolygon(eastFace);
            g2.setColor(new Color(255, 255, 255, 18));
            g2.drawPolygon(eastFace);
        }

        if (!world.hasBlock(x, y, z + 1)) {
            Polygon southFace = polygon(topSw, topSe, baseSe, baseSw);
            g2.setColor(blockType.leftColor());
            g2.fillPolygon(southFace);
            g2.setColor(new Color(255, 255, 255, 18));
            g2.drawPolygon(southFace);
        }

        if (!world.hasBlock(x - 1, y, z)) {
            Polygon westFace = polygon(topNw, topSw, baseSw, baseNw);
            g2.setColor(blockType.leftColor());
            g2.fillPolygon(westFace);
            g2.setColor(new Color(255, 255, 255, 16));
            g2.drawPolygon(westFace);
        }

        if (!world.hasBlock(x, y, z - 1)) {
            Polygon northFace = polygon(topNw, topNe, baseNe, baseNw);
            g2.setColor(blockType.rightColor());
            g2.fillPolygon(northFace);
            g2.setColor(new Color(255, 255, 255, 16));
            g2.drawPolygon(northFace);
        }

        if (!world.hasBlock(x, y + 1, z)) {
            Polygon topFace = polygon(topNw, topNe, topSe, topSw);
            g2.setColor(blockType.topColor());
            g2.fillPolygon(topFace);
            g2.setColor(new Color(255, 255, 255, 22));
            g2.drawPolygon(topFace);
        }
    }

    private double depthForBlock(Player player, double cameraYaw, double worldX, double worldY, double worldZ) {
        double rotatedX = rotatedX(player, cameraYaw, worldX, worldZ);
        double rotatedZ = rotatedZ(player, cameraYaw, worldX, worldZ);
        return rotatedX + rotatedZ + worldY * 0.1;
    }

    private Point2D.Double project(
        Player player,
        double cameraYaw,
        int panelWidth,
        int panelHeight,
        double worldX,
        double worldY,
        double worldZ
    ) {
        double rx = rotatedX(player, cameraYaw, worldX, worldZ);
        double rz = rotatedZ(player, cameraYaw, worldX, worldZ);
        double screenX = panelWidth / 2.0 + (rx - rz) * TILE_WIDTH * 0.5;
        double screenY = panelHeight * 0.64 + (rx + rz) * TILE_HEIGHT * 0.5 - worldY * BLOCK_HEIGHT;
        return new Point2D.Double(screenX, screenY);
    }

    private Polygon topFacePolygon(
        Player player,
        double cameraYaw,
        int panelWidth,
        int panelHeight,
        int x,
        int y,
        int z
    ) {
        Point2D.Double topNw = project(player, cameraYaw, panelWidth, panelHeight, x, y + 1, z);
        Point2D.Double topNe = project(player, cameraYaw, panelWidth, panelHeight, x + 1, y + 1, z);
        Point2D.Double topSe = project(player, cameraYaw, panelWidth, panelHeight, x + 1, y + 1, z + 1);
        Point2D.Double topSw = project(player, cameraYaw, panelWidth, panelHeight, x, y + 1, z + 1);
        return polygon(topNw, topNe, topSe, topSw);
    }

    private double rotatedX(Player player, double cameraYaw, double worldX, double worldZ) {
        double dx = worldX - player.x;
        double dz = worldZ - player.z;
        double cos = Math.cos(cameraYaw);
        double sin = Math.sin(cameraYaw);
        return dx * cos - dz * sin;
    }

    private double rotatedZ(Player player, double cameraYaw, double worldX, double worldZ) {
        double dx = worldX - player.x;
        double dz = worldZ - player.z;
        double cos = Math.cos(cameraYaw);
        double sin = Math.sin(cameraYaw);
        return dx * sin + dz * cos;
    }

    private Polygon polygon(Point2D.Double... points) {
        int[] xs = new int[points.length];
        int[] ys = new int[points.length];
        for (int index = 0; index < points.length; index += 1) {
            xs[index] = (int) Math.round(points[index].x);
            ys[index] = (int) Math.round(points[index].y);
        }
        return new Polygon(xs, ys, points.length);
    }
}
