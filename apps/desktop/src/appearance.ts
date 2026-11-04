export const TITLE_BAR_HEIGHT = 32;
export type Appearance = { background: string; foreground: string; dark: boolean };
export const LIGHT_APPEARANCE: Appearance = { background: '#f7f7f8', foreground: '#171719', dark: false };
export const DARK_APPEARANCE: Appearance = { background: '#1b1b1b', foreground: '#f1f1f1', dark: true };

/** 渲染器只可报告两个颜色值，不接受CSS文本、URL或任何窗口操作。 */
export function readAppearance(value: unknown): Appearance | undefined {
  if (!value || typeof value !== 'object') return;
  const { background, foreground } = value as Record<string, unknown>;
  if (typeof background !== 'string' || typeof foreground !== 'string' ||
      !/^#[0-9a-f]{6}$/i.test(background) || !/^#[0-9a-f]{6}$/i.test(foreground)) return;
  const rgb = [1, 3, 5].map(at => parseInt(background.slice(at, at + 2), 16));
  return { background: background.toLowerCase(), foreground: foreground.toLowerCase(), dark: rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722 < 128 };
}
