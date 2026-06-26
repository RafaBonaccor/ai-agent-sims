package blockforge;

public final class Player {
    public double x;
    public double y;
    public double z;
    public double verticalVelocity;
    public boolean onGround;

    public void respawn(World.SpawnPoint spawnPoint) {
        x = spawnPoint.x();
        y = spawnPoint.y();
        z = spawnPoint.z();
        verticalVelocity = 0;
        onGround = true;
    }
}
