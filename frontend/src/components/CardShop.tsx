import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import cardSheet from "@/assets/cards/balatro_cards.png";
import bluePack from "@/assets/packs/blue.png";
import greenPack from "@/assets/packs/green.png";
import orangePack from "@/assets/packs/orange.png";
import redPack from "@/assets/packs/red.png";
import { SKIN_COORDS, type CardSkin } from "./Card";
import { play } from "@/audio/useSound";

const SKINS: CardSkin[] = ["default", "gray", "blue", "yellow", "green", "fade", "ancient", "maze", "stars", "wedges", "transit"];
const PACKS = [bluePack, greenPack, orangePack, redPack];
type ShopState = { balance: number; equipped_skin: CardSkin; owned: CardSkin[] };
type RewardReveal = { skin: CardSkin; duplicate: boolean; refund: number };
const CURRENCY_COORD = [4, 4] as const; // Sheet coordinate (5, 5), converted to zero-based indices.
const CURRENCY_SPRITE_CENTER = [27, 28] as const;

async function shopRequest(path: string, body?: unknown) {
  const response = await fetch(`/api/shop${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? "Card shop request failed");
  return data;
}

function skinStyle(skin: CardSkin, scale = 1) {
  const [col, row] = SKIN_COORDS[skin];
  return {
    backgroundImage: `url("${cardSheet.src}")`,
    backgroundSize: `${cardSheet.width * scale}px ${cardSheet.height * scale}px`,
    backgroundPosition: `${-col * 71 * scale}px ${-row * 95 * scale}px`,
  };
}

function currencyStyle() {
  const scale = 0.6;
  const [col, row] = CURRENCY_COORD;
  const [spriteCenterX, spriteCenterY] = CURRENCY_SPRITE_CENTER;
  const iconCenter = 11;
  return {
    backgroundImage: `url("${cardSheet.src}")`,
    backgroundSize: `${cardSheet.width * scale}px ${cardSheet.height * scale}px`,
    backgroundPosition: `${iconCenter - (col * 71 + spriteCenterX) * scale}px ${iconCenter - (row * 95 + spriteCenterY) * scale}px`,
  };
}

function Currency({ children }: { children: ReactNode }) {
  return <span className="shop-currency"><span className="shop-currency-icon" style={currencyStyle()} aria-hidden="true" /><span className="shop-currency-label">{children}</span></span>;
}

export default function CardShop({ onBack, onSkinChange }: { onBack: () => void; onSkinChange: (skin: CardSkin) => void }) {
  const [shop, setShop] = useState<ShopState | null>(null);
  const [rewardReveal, setRewardReveal] = useState<RewardReveal | null>(null);
  const [packImage, setPackImage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function refresh() { setShop(await shopRequest("")); }
  useEffect(() => {
    setPackImage(PACKS[Math.floor(Math.random() * PACKS.length)].src);
    refresh().catch((e) => setError(e.message));
  }, []);

  async function openCase() {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await shopRequest("/roll", {});
      setShop(result);
      if (result.reward) {
        play(result.duplicate ? "gacha.dupe" : "gacha.hit");
        setRewardReveal({ skin: result.reward, duplicate: result.duplicate, refund: result.refund });
      } else {
        play("gacha.nothing");
        setNotice("No skin this time. Try again!");
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Could not open case"); }
    finally { setBusy(false); }
  }

  async function equip(skin: CardSkin) {
    if (!shop?.owned.includes(skin)) return;
    setBusy(true); setError("");
    try {
      const result = await shopRequest("/equip", { skin });
      setShop(result); onSkinChange(skin);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not equip skin"); }
    finally { setBusy(false); }
  }

  return <main className="shop-page">
    <header className="shop-header"><button className="btn btn-orange" onClick={onBack}>Back</button><h1 className="title-text">Card Shop</h1><strong className="shop-balance">{shop ? <Currency>{shop.balance} aircoin</Currency> : "Loading…"}</strong></header>
    <div className="shop-layout">
      <section className="shop-case glass" aria-label="Open a case">
        <div className="case-square">{packImage && <img src={packImage} alt="Card pack" />}</div>
        <p className="case-odds">80% nothing <span>·</span> 15% common <span>·</span> 5% rare</p>
        <button className="btn btn-green case-open-button" disabled={!shop || busy || shop.balance < 10} onClick={openCase}>{busy ? "Opening…" : <>Open Pack · <Currency>10 aircoin</Currency></>}</button>
        {notice && <p className="shop-notice" role="status">{notice}</p>}{error && <p className="error-text" role="alert">{error}</p>}
      </section>
      <section className="shop-inventory glass" aria-label="Card skin collection">
        <div className="skin-grid">{SKINS.map((skin) => {
          const owned = shop?.owned.includes(skin) ?? false;
          return <button key={skin} className={`skin-tile${owned ? " owned" : " unowned"}${shop?.equipped_skin === skin ? " equipped" : ""}`} onClick={() => equip(skin)} disabled={!owned || busy} aria-label={`${skin}${owned ? shop?.equipped_skin === skin ? ", equipped" : ", equip" : ", unowned"}`}>
            <span className="skin-sprite-frame"><span className="skin-sprite" style={skinStyle(skin)} aria-hidden="true" /></span>{!owned && <span className="skin-lock">Unowned</span>}
            <span className="skin-name">{skin}</span>{shop?.equipped_skin === skin && <span className="skin-equipped">Equipped</span>}
          </button>;
        })}</div>
      </section>
    </div>
    {rewardReveal && typeof document !== "undefined" && createPortal(<div className="shop-reward-backdrop">
      <section className="shop-reward glass" role="dialog" aria-modal="true" aria-labelledby="shop-reward-title">
        <h2 id="shop-reward-title">{rewardReveal.duplicate ? "Duplicate skin" : `You got ${rewardReveal.skin}!`}</h2>
        <span className="shop-reward-sprite" style={skinStyle(rewardReveal.skin, 2)} aria-hidden="true" />
        <p>{rewardReveal.duplicate
          ? `You already own ${rewardReveal.skin}. Your ${rewardReveal.refund} aircoin pull was refunded.`
          : `${rewardReveal.skin} was added to your collection.`}</p>
        <button className="btn btn-green" onClick={() => setRewardReveal(null)}>Continue</button>
      </section>
    </div>, document.body)}
  </main>;
}
