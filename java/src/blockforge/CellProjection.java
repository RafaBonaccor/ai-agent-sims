package blockforge;

import java.awt.Polygon;

record CellProjection(int x, int y, int z, double depth, Polygon topFace, boolean topVisible) {
}
