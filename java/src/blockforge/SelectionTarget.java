package blockforge;

import java.awt.Polygon;

record SelectionTarget(
    int blockX,
    int blockY,
    int blockZ,
    int placeX,
    int placeY,
    int placeZ,
    boolean inReach,
    Polygon topFace,
    double distance
) {
}
