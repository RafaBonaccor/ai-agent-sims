package blockforge;

import java.awt.Color;
import java.util.ArrayList;
import java.util.List;

final class GreedyMesher {
    private GreedyMesher() {
    }

    static ChunkMesh buildChunkMesh(World world, World.WorldChunk chunk) {
        List<MeshFace> faces = new ArrayList<>();
        addTopFaces(faces, world, chunk);
        addBottomFaces(faces, world, chunk);
        addEastWestFaces(faces, world, chunk, Orientation.EAST);
        addEastWestFaces(faces, world, chunk, Orientation.WEST);
        addNorthSouthFaces(faces, world, chunk, Orientation.SOUTH);
        addNorthSouthFaces(faces, world, chunk, Orientation.NORTH);
        return new ChunkMesh(chunk.chunkX(), chunk.chunkZ(), world.chunkRevision(chunk), List.copyOf(faces));
    }

    private static void addTopFaces(List<MeshFace> faces, World world, World.WorldChunk chunk) {
        for (int y = world.minBlockY(); y <= world.maxBlockY(); y += 1) {
            addHorizontalFaces(faces, world, chunk, y, Orientation.TOP);
        }
    }

    private static void addBottomFaces(List<MeshFace> faces, World world, World.WorldChunk chunk) {
        for (int y = world.minBlockY(); y <= world.maxBlockY(); y += 1) {
            addHorizontalFaces(faces, world, chunk, y, Orientation.BOTTOM);
        }
    }

    private static void addHorizontalFaces(
        List<MeshFace> faces,
        World world,
        World.WorldChunk chunk,
        int y,
        Orientation orientation
    ) {
        int width = chunk.maxX() - chunk.minX() + 1;
        int depth = chunk.maxZ() - chunk.minZ() + 1;
        boolean[][] consumed = new boolean[width][depth];

        for (int localZ = 0; localZ < depth; localZ += 1) {
            for (int localX = 0; localX < width; localX += 1) {
                if (consumed[localX][localZ]) {
                    continue;
                }

                int x = chunk.minX() + localX;
                int z = chunk.minZ() + localZ;
                BlockType blockType = exposedHorizontalType(world, x, y, z, orientation);
                if (blockType == null) {
                    consumed[localX][localZ] = true;
                    continue;
                }

                int faceWidth = growHorizontalWidth(world, consumed, chunk, localX, localZ, width, y, orientation, blockType);
                int faceDepth = growHorizontalDepth(
                    world,
                    consumed,
                    chunk,
                    localX,
                    localZ,
                    faceWidth,
                    depth,
                    y,
                    orientation,
                    blockType
                );

                markConsumed(consumed, localX, localZ, faceWidth, faceDepth);
                faces.add(new MeshFace(orientation, x, y, z, faceWidth, faceDepth, blockType, meshFaceColor(world, orientation, x, y, z, faceWidth, faceDepth, blockType)));
            }
        }
    }

    private static int growHorizontalWidth(
        World world,
        boolean[][] consumed,
        World.WorldChunk chunk,
        int startX,
        int startZ,
        int maxWidth,
        int y,
        Orientation orientation,
        BlockType blockType
    ) {
        int width = 0;
        while (startX + width < maxWidth) {
            if (consumed[startX + width][startZ]) {
                break;
            }

            int x = chunk.minX() + startX + width;
            int z = chunk.minZ() + startZ;
            if (exposedHorizontalType(world, x, y, z, orientation) != blockType) {
                break;
            }
            width += 1;
        }
        return width;
    }

    private static int growHorizontalDepth(
        World world,
        boolean[][] consumed,
        World.WorldChunk chunk,
        int startX,
        int startZ,
        int faceWidth,
        int maxDepth,
        int y,
        Orientation orientation,
        BlockType blockType
    ) {
        int depth = 1;
        while (startZ + depth < maxDepth) {
            for (int offsetX = 0; offsetX < faceWidth; offsetX += 1) {
                if (consumed[startX + offsetX][startZ + depth]) {
                    return depth;
                }

                int x = chunk.minX() + startX + offsetX;
                int z = chunk.minZ() + startZ + depth;
                if (exposedHorizontalType(world, x, y, z, orientation) != blockType) {
                    return depth;
                }
            }
            depth += 1;
        }
        return depth;
    }

    private static BlockType exposedHorizontalType(World world, int x, int y, int z, Orientation orientation) {
        BlockType blockType = world.blockAt(x, y, z);
        if (blockType == null) {
            return null;
        }

        int neighborY = orientation == Orientation.TOP ? y + 1 : y - 1;
        return world.hasBlock(x, neighborY, z) ? null : blockType;
    }

    private static void addEastWestFaces(
        List<MeshFace> faces,
        World world,
        World.WorldChunk chunk,
        Orientation orientation
    ) {
        for (int x = chunk.minX(); x <= chunk.maxX(); x += 1) {
            int depth = chunk.maxZ() - chunk.minZ() + 1;
            int height = world.maxBlockY() - world.minBlockY() + 1;
            boolean[][] consumed = new boolean[depth][height];

            for (int localY = 0; localY < height; localY += 1) {
                for (int localZ = 0; localZ < depth; localZ += 1) {
                    if (consumed[localZ][localY]) {
                        continue;
                    }

                    int y = world.minBlockY() + localY;
                    int z = chunk.minZ() + localZ;
                    BlockType blockType = exposedEastWestType(world, x, y, z, orientation);
                    if (blockType == null) {
                        consumed[localZ][localY] = true;
                        continue;
                    }

                    int faceWidth = growEastWestWidth(world, consumed, chunk, x, localZ, localY, depth, orientation, blockType);
                    int faceHeight = growEastWestHeight(
                        world,
                        consumed,
                        chunk,
                        x,
                        localZ,
                        localY,
                        faceWidth,
                        height,
                        orientation,
                        blockType
                    );

                    markConsumed(consumed, localZ, localY, faceWidth, faceHeight);
                    faces.add(new MeshFace(orientation, x, y, z, faceWidth, faceHeight, blockType, meshFaceColor(world, orientation, x, y, z, faceWidth, faceHeight, blockType)));
                }
            }
        }
    }

    private static int growEastWestWidth(
        World world,
        boolean[][] consumed,
        World.WorldChunk chunk,
        int x,
        int startZ,
        int startY,
        int maxWidth,
        Orientation orientation,
        BlockType blockType
    ) {
        int width = 0;
        while (startZ + width < maxWidth) {
            if (consumed[startZ + width][startY]) {
                break;
            }

            int z = chunk.minZ() + startZ + width;
            int y = world.minBlockY() + startY;
            if (exposedEastWestType(world, x, y, z, orientation) != blockType) {
                break;
            }
            width += 1;
        }
        return width;
    }

    private static int growEastWestHeight(
        World world,
        boolean[][] consumed,
        World.WorldChunk chunk,
        int x,
        int startZ,
        int startY,
        int faceWidth,
        int maxHeight,
        Orientation orientation,
        BlockType blockType
    ) {
        int height = 1;
        while (startY + height < maxHeight) {
            for (int offsetZ = 0; offsetZ < faceWidth; offsetZ += 1) {
                if (consumed[startZ + offsetZ][startY + height]) {
                    return height;
                }

                int z = chunk.minZ() + startZ + offsetZ;
                int y = world.minBlockY() + startY + height;
                if (exposedEastWestType(world, x, y, z, orientation) != blockType) {
                    return height;
                }
            }
            height += 1;
        }
        return height;
    }

    private static BlockType exposedEastWestType(World world, int x, int y, int z, Orientation orientation) {
        BlockType blockType = world.blockAt(x, y, z);
        if (blockType == null) {
            return null;
        }

        int neighborX = orientation == Orientation.EAST ? x + 1 : x - 1;
        return world.hasBlock(neighborX, y, z) ? null : blockType;
    }

    private static void addNorthSouthFaces(
        List<MeshFace> faces,
        World world,
        World.WorldChunk chunk,
        Orientation orientation
    ) {
        for (int z = chunk.minZ(); z <= chunk.maxZ(); z += 1) {
            int width = chunk.maxX() - chunk.minX() + 1;
            int height = world.maxBlockY() - world.minBlockY() + 1;
            boolean[][] consumed = new boolean[width][height];

            for (int localY = 0; localY < height; localY += 1) {
                for (int localX = 0; localX < width; localX += 1) {
                    if (consumed[localX][localY]) {
                        continue;
                    }

                    int x = chunk.minX() + localX;
                    int y = world.minBlockY() + localY;
                    BlockType blockType = exposedNorthSouthType(world, x, y, z, orientation);
                    if (blockType == null) {
                        consumed[localX][localY] = true;
                        continue;
                    }

                    int faceWidth = growNorthSouthWidth(world, consumed, chunk, localX, localY, z, width, orientation, blockType);
                    int faceHeight = growNorthSouthHeight(
                        world,
                        consumed,
                        chunk,
                        localX,
                        localY,
                        z,
                        faceWidth,
                        height,
                        orientation,
                        blockType
                    );

                    markConsumed(consumed, localX, localY, faceWidth, faceHeight);
                    faces.add(new MeshFace(orientation, x, y, z, faceWidth, faceHeight, blockType, meshFaceColor(world, orientation, x, y, z, faceWidth, faceHeight, blockType)));
                }
            }
        }
    }

    private static int growNorthSouthWidth(
        World world,
        boolean[][] consumed,
        World.WorldChunk chunk,
        int startX,
        int startY,
        int z,
        int maxWidth,
        Orientation orientation,
        BlockType blockType
    ) {
        int width = 0;
        while (startX + width < maxWidth) {
            if (consumed[startX + width][startY]) {
                break;
            }

            int x = chunk.minX() + startX + width;
            int y = world.minBlockY() + startY;
            if (exposedNorthSouthType(world, x, y, z, orientation) != blockType) {
                break;
            }
            width += 1;
        }
        return width;
    }

    private static int growNorthSouthHeight(
        World world,
        boolean[][] consumed,
        World.WorldChunk chunk,
        int startX,
        int startY,
        int z,
        int faceWidth,
        int maxHeight,
        Orientation orientation,
        BlockType blockType
    ) {
        int height = 1;
        while (startY + height < maxHeight) {
            for (int offsetX = 0; offsetX < faceWidth; offsetX += 1) {
                if (consumed[startX + offsetX][startY + height]) {
                    return height;
                }

                int x = chunk.minX() + startX + offsetX;
                int y = world.minBlockY() + startY + height;
                if (exposedNorthSouthType(world, x, y, z, orientation) != blockType) {
                    return height;
                }
            }
            height += 1;
        }
        return height;
    }

    private static BlockType exposedNorthSouthType(World world, int x, int y, int z, Orientation orientation) {
        BlockType blockType = world.blockAt(x, y, z);
        if (blockType == null) {
            return null;
        }

        int neighborZ = orientation == Orientation.SOUTH ? z + 1 : z - 1;
        return world.hasBlock(x, y, neighborZ) ? null : blockType;
    }

    private static void markConsumed(boolean[][] consumed, int startA, int startB, int width, int height) {
        for (int offsetB = 0; offsetB < height; offsetB += 1) {
            for (int offsetA = 0; offsetA < width; offsetA += 1) {
                consumed[startA + offsetA][startB + offsetB] = true;
            }
        }
    }

    private static Color meshFaceColor(
        World world,
        Orientation orientation,
        int x,
        int y,
        int z,
        int width,
        int height,
        BlockType blockType
    ) {
        return switch (orientation) {
            case TOP -> topFaceColorWithAmbientOcclusion(world, x, y, z, width, height, blockType);
            case EAST, SOUTH -> blockType.rightColor();
            case WEST, NORTH, BOTTOM -> blockType.leftColor();
        };
    }

    private static Color topFaceColorWithAmbientOcclusion(
        World world,
        int faceX,
        int faceY,
        int faceZ,
        int width,
        int height,
        BlockType blockType
    ) {
        int y = faceY + 1;
        int blockers = 0;
        int samples = 0;

        for (int x = faceX - 1; x <= faceX + width; x += 1) {
            blockers += world.hasBlock(x, y, faceZ - 1) ? 1 : 0;
            blockers += world.hasBlock(x, y, faceZ + height) ? 1 : 0;
            samples += 2;
        }

        for (int z = faceZ; z < faceZ + height; z += 1) {
            blockers += world.hasBlock(faceX - 1, y, z) ? 1 : 0;
            blockers += world.hasBlock(faceX + width, y, z) ? 1 : 0;
            samples += 2;
        }

        double occlusion = samples == 0 ? 0 : Math.min(0.28, blockers / (double) samples * 0.55);
        return shade(blockType.topColor(), 1.0 - occlusion);
    }

    private static Color shade(Color color, double factor) {
        int red = (int) Math.round(color.getRed() * factor);
        int green = (int) Math.round(color.getGreen() * factor);
        int blue = (int) Math.round(color.getBlue() * factor);
        return new Color(
            Math.max(0, Math.min(255, red)),
            Math.max(0, Math.min(255, green)),
            Math.max(0, Math.min(255, blue))
        );
    }

    enum Orientation {
        TOP,
        BOTTOM,
        EAST,
        WEST,
        SOUTH,
        NORTH
    }

    record MeshFace(Orientation orientation, int x, int y, int z, int width, int height, BlockType blockType, Color color) {
    }

    record ChunkMesh(int chunkX, int chunkZ, int revision, List<MeshFace> faces) {
    }
}
