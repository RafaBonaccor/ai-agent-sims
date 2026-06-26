package blockforge;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

final class SaveGame {
    private static final int VERSION = 1;
    private static final String BLOCK_PREFIX = "block.";

    private SaveGame() {
    }

    static Path defaultPath() {
        return Path.of(System.getProperty("user.dir"), "java", "save", "blockforge.properties");
    }

    static void save(
        Path path,
        World world,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int activeBlockIndex,
        int deathCount,
        ViewMode viewMode,
        boolean autoStepEnabled
    ) throws IOException {
        Properties properties = new Properties();
        properties.setProperty("version", Integer.toString(VERSION));
        properties.setProperty("world.radius", Integer.toString(world.radius()));
        properties.setProperty("player.x", Double.toString(player.x));
        properties.setProperty("player.y", Double.toString(player.y));
        properties.setProperty("player.z", Double.toString(player.z));
        properties.setProperty("player.verticalVelocity", Double.toString(player.verticalVelocity));
        properties.setProperty("player.onGround", Boolean.toString(player.onGround));
        properties.setProperty("camera.yaw", Double.toString(cameraYaw));
        properties.setProperty("camera.pitch", Double.toString(cameraPitch));
        properties.setProperty("hotbar.active", Integer.toString(activeBlockIndex));
        properties.setProperty("stats.deaths", Integer.toString(deathCount));
        properties.setProperty("view.mode", viewMode.name());
        properties.setProperty("settings.autoStep", Boolean.toString(autoStepEnabled));

        world.forEachBlock((x, y, z, blockType) ->
            properties.setProperty(BLOCK_PREFIX + x + "," + y + "," + z, blockType.name())
        );

        Files.createDirectories(path.getParent());
        try (OutputStream output = Files.newOutputStream(path)) {
            properties.store(output, "Blockforge save file");
        }
    }

    static LoadedGame load(Path path) throws IOException {
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(path)) {
            properties.load(input);
        }

        int version = integer(properties, "version", VERSION);
        if (version != VERSION) {
            throw new IOException("Versione salvataggio non supportata: " + version);
        }

        int radius = integer(properties, "world.radius", 22);
        World world = new World(radius);
        world.clearBlocks();

        for (String propertyName : properties.stringPropertyNames()) {
            if (!propertyName.startsWith(BLOCK_PREFIX)) {
                continue;
            }

            String[] coordinates = propertyName.substring(BLOCK_PREFIX.length()).split(",");
            if (coordinates.length != 3) {
                continue;
            }

            int x = Integer.parseInt(coordinates[0]);
            int y = Integer.parseInt(coordinates[1]);
            int z = Integer.parseInt(coordinates[2]);
            BlockType blockType = BlockType.valueOf(properties.getProperty(propertyName));
            world.setBlock(x, y, z, blockType);
        }

        Player player = new Player();
        player.x = decimal(properties, "player.x", 0.5);
        player.y = decimal(properties, "player.y", 8.0);
        player.z = decimal(properties, "player.z", 0.5);
        player.verticalVelocity = decimal(properties, "player.verticalVelocity", 0);
        player.onGround = Boolean.parseBoolean(properties.getProperty("player.onGround", "true"));

        return new LoadedGame(
            world,
            player,
            decimal(properties, "camera.yaw", Math.toRadians(35)),
            decimal(properties, "camera.pitch", -0.1),
            integer(properties, "hotbar.active", 0),
            integer(properties, "stats.deaths", 0),
            ViewMode.valueOf(properties.getProperty("view.mode", ViewMode.SUPERIOR.name())),
            Boolean.parseBoolean(properties.getProperty("settings.autoStep", "false"))
        );
    }

    private static int integer(Properties properties, String key, int fallback) {
        return Integer.parseInt(properties.getProperty(key, Integer.toString(fallback)));
    }

    private static double decimal(Properties properties, String key, double fallback) {
        return Double.parseDouble(properties.getProperty(key, Double.toString(fallback)));
    }

    record LoadedGame(
        World world,
        Player player,
        double cameraYaw,
        double cameraPitch,
        int activeBlockIndex,
        int deathCount,
        ViewMode viewMode,
        boolean autoStepEnabled
    ) {
    }
}
