package blockforge;

import java.awt.Color;

public enum BlockType {
    GRASS("Erba", new Color(108, 185, 91)),
    DIRT("Terra", new Color(122, 81, 52)),
    STONE("Pietra", new Color(141, 149, 160)),
    WOOD("Legno", new Color(156, 106, 54)),
    GLOW("Luce", new Color(246, 214, 110));

    private final String label;
    private final Color topColor;

    BlockType(String label, Color topColor) {
        this.label = label;
        this.topColor = topColor;
    }

    public String label() {
        return label;
    }

    public Color topColor() {
        return topColor;
    }

    public Color leftColor() {
        return shade(topColor, 0.78);
    }

    public Color rightColor() {
        return shade(topColor, 0.62);
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
}
