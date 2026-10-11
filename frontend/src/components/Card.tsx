import type { CSSProperties } from "react";
import facesSheet from "@/assets/standard/balatro_std_faces.png";
import cardSheet from "@/assets/cards/balatro_cards.png";

const RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"];
const SUITS = ["hearts", "clubs", "diamonds", "spades"];

// Sprite cell size in the source sheets, and the default display scale.
const CELL_W = 71;
const CELL_H = 95;
const SCALE = 2;

export type CardSkin = "default" | "gray" | "blue" | "yellow" | "green" | "fade" | "ancient" | "maze" | "stars" | "wedges" | "transit";
export const SKIN_COORDS: Record<CardSkin, [number, number]> = {
  // Convert the 1-based grid coordinates used for this sheet to zero-based
  // sprite indices. Each cell is 71x95 pixels.
  default: [0, 0], gray: [3, 2], blue: [0, 2], yellow: [1, 2], green: [2, 2],
  fade: [5, 2], ancient: [4, 1], maze: [0, 4], stars: [3, 4], wedges: [2, 4], transit: [1, 4],
};

export const CARD_W = CELL_W * SCALE;
export const CARD_H = CELL_H * SCALE;

/** Pixel size of one card at the given display scale. */
export const cardSize = (scale: number) => ({ width: CELL_W * scale, height: CELL_H * scale });

function spriteStyle(
  sheet: { src: string; width: number; height: number },
  col: number,
  row: number,
  scale: number,
): CSSProperties {
  const { width, height } = cardSize(scale);
  return {
    backgroundImage: `url("${sheet.src}")`,
    backgroundSize: `${sheet.width * scale}px ${sheet.height * scale}px`,
    backgroundPosition: `-${col * width}px -${row * height}px`,
    imageRendering: "pixelated",
  };
}

export function EmptySlot({ scale = SCALE }: { scale?: number }) {
  return <div className="card-slot-empty" style={cardSize(scale)} />;
}

/**
 * A card that slides in (face-down) when it mounts and flips face-up when
 * `faceUp` becomes true. `card` may be undefined while the face is still
 * unknown to the client (the dealer's hole card).
 */
export default function Card({
  card,
  faceUp,
  glow = false,
  scale = SCALE,
  skin = "default",
}: {
  card?: string;
  faceUp: boolean;
  glow?: boolean;
  scale?: number;
  skin?: CardSkin;
}) {
  const [rank, , suit] = card ? card.split(" ") : [];
  const front = card
    ? spriteStyle(facesSheet, RANKS.indexOf(rank), SUITS.indexOf(suit), scale)
    : undefined;

  return (
    <div className={`card-slot deal-in${glow ? " card-glow" : ""}`} style={cardSize(scale)}>
      <div className={`card-flipper${faceUp ? "" : " is-down"}`}>
        <div
          className="card-face card-front"
          role="img"
          aria-label={faceUp && card ? card : "Face-down card"}
          style={front}
        />
        <div className="card-face card-back" aria-hidden style={spriteStyle(cardSheet, ...SKIN_COORDS[skin], scale)} />
      </div>
    </div>
  );
}
