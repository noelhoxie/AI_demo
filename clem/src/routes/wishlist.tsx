import { createFileRoute, Link } from "@tanstack/react-router";
import { useRef, useState, useMemo, useEffect } from "react";
import { Heart, Link2, Loader2, Search, ShirtIcon, ExternalLink, X, Camera, Sparkles, ArrowUpRight } from "lucide-react";
import { PageShell } from "@/components/vesti/PageShell";
import { useCloset, closet } from "@/lib/vesti/store";
import { useProfile } from "@/lib/vesti/profile";
import { scrapeProduct, searchProducts, identifyFromImage, type ScrapedItem } from "@/lib/api/wishlist.functions";

export const Route = createFileRoute("/wishlist")({
  head: () => ({
    meta: [
      { title: "Curate — Clem" },
      { name: "description", content: "Save pieces you love from any online store." },
    ],
  }),
  validateSearch: (search: Record<string, unknown>) => ({
    mode: typeof search.mode === "string" ? search.mode : "wishlist",
  }),
  component: WishlistPage,
});

type Mode = "wishlist" | "discover";

function WishImg({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="w-full h-full grid place-items-center text-muted-foreground">
        <Heart className="size-5 opacity-40" />
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

function getProfileChips(profile: ReturnType<typeof useProfile>["profile"]): string[] {
  const out: string[] = [];
  const [color1, color2] = profile.colors;
  const [style1] = profile.styleIdentities;
  const [brand1] = profile.brands;
  if (color1) out.push(`${color1} linen blazer`);
  if (color1) out.push(`${color1} wide leg trousers`);
  if (style1 === "quiet luxury") out.push("quiet luxury summer dress");
  else if (style1 === "minimalist") out.push("minimalist wardrobe basics");
  else if (style1) out.push(`${style1} style pieces`);
  if (brand1) out.push(brand1);
  if (color2 && out.length < 4) out.push(`${color2} heeled mules`);
  return out.slice(0, 4);
}

function buildProfileQuery(profile: ReturnType<typeof useProfile>["profile"]): string | null {
  const parts: string[] = [];
  if (profile.styleIdentities[0]) parts.push(profile.styleIdentities[0]);
  if (profile.colors[0]) parts.push(profile.colors[0]);
  if (profile.occasions[0]) parts.push(profile.occasions[0]);
  if (parts.length === 0) return null;
  parts.push("clothing buy shop");
  return parts.join(" ");
}

interface PhotoRec {
  name: string;
  brand: string;
  category: string;
  priceRange: string;
  why: string;
}

function shopUrl(brand: string, name: string, index = 0): string {
  const q = encodeURIComponent(`${brand} ${name}`);
  const nq = encodeURIComponent(name);
  const b = brand.toLowerCase();
  // Luxury / investment pieces → Net-A-Porter
  const netaporter = ["the row","celine","loewe","bottega veneta","jacquemus","khaite","toteme","max mara","acne studios","prada","gucci","miu miu","valentino","dior","saint laurent","givenchy","isabel marant","officine générale","nanushka","nili lotan","equipment","a.p.c.","zimmermann","staud","mansur gavriel","veronica beard","l'agence","vince","loro piana","brunello cucinelli","missoni","emilio pucci","alberta ferretti","oscar de la renta","carolina herrera","ulla johnson","saloni","rixo","erdem","roksanda","roland mouret","emilia wickstead","jenny packham","temperley","mother of pearl","raey","shrimps","galvan","proenza schouler","altuzarra","chloé","chloe","stella mccartney","burberry","alexander mcqueen","roberto cavalli","versace","dolce & gabbana","fendi","moschino","etro","paul smith","vivienne westwood","comme des garçons","issey miyake","jil sander","marni","balenciaga","maison margiela","off-white","palm angels","ami paris","anine bing","diane von furstenberg","dvf","alice + olivia","joie","rebecca taylor","ba&sh","faithfull the brand","réalisation par","see by chloé","l.k. bennett","lk bennett"];
  // Contemporary designer → SSENSE
  const ssense = ["ganni","rag & bone","theory","tibi","rotate","sea new york","sandy liang","frame","doên","by malene birger","iro paris","iro","zadig & voltaire","the kooples","gerard darel","rouje","sézane","sezane","aje","alemais","esse studios","bec & bridge","posse","alice mccall","allsaints","all saints","reiss","whistles","phase eight","mint velvet","ted baker","french connection","karen millen","coast"];
  // H&M group
  const hm = ["h&m","h & m","hennes & mauritz","h&m divided","& other stories","other stories","weekday","monki","afound"];
  // Uniqlo / Fast Retailing
  const uniqlo = ["uniqlo"];
  // Gap Inc
  const gap = ["gap","banana republic","old navy","athleta","intermix"];
  // J.Crew / Madewell
  const jcrew = ["j.crew","j crew","jcrew","madewell","crewcuts"];
  // Lululemon
  const lulul = ["lululemon","lulu lemon","lululemon athletica"];
  // Nike
  const nike = ["nike","jordan brand","air jordan"];
  // Adidas
  const adidas = ["adidas","adidas originals","adidas by stella mccartney"];
  // Target-owned labels
  const target = ["target","a new day","knox rose","who what wear","universal thread","stars above","colsie","all in motion"];
  // Everlane
  const everlane = ["everlane"];
  // Reformation
  const reformation = ["reformation"];
  // Abercrombie & Fitch group
  const abercrombie = ["abercrombie","hollister","gilly hicks"];
  // American Eagle / Aerie
  const ae = ["american eagle","aerie"];
  // Express
  const express_ = ["express"];
  // Ann Taylor / LOFT / sister brands
  const anntaylor = ["ann taylor","anntaylor","loft","lou & grey","talbots","j.jill","j jill","chico's","chicos","white house black market","whbm","soma","cabi"];
  // Ralph Lauren / Tommy Hilfiger
  const rl = ["ralph lauren","polo ralph lauren","lauren ralph lauren","double rl","rrl","tommy hilfiger","tommy jeans"];
  // Michael Kors / Kate Spade / Coach
  const tapestry = ["michael kors","kate spade","coach","stuart weitzman"];
  // Tory Burch
  const toryburch = ["tory burch","tory sport"];
  // Calvin Klein / DKNY
  const pvh = ["calvin klein","dkny","donna karan"];
  // Athletic / outdoor brands
  const ua = ["under armour","underarmour"];
  const puma = ["puma"];
  const reebok = ["reebok"];
  const nb = ["new balance"];
  const vans = ["vans"];
  const converse = ["converse"];
  const tnf = ["the north face","north face"];
  const patagonia = ["patagonia"];
  const alo = ["alo yoga","alo moves"];
  const vuori = ["vuori"];
  // Revolve / boho-contemporary
  const revolve = ["revolve","for love & lemons","astr the label","l*space","lovers + friends","free people","show me your mumu","loveshackfancy","love shack fancy","z supply","superdown","princess polly","showpo","lulus","billabong","o'neill","roxy","volcom","bdg"];
  // ASOS / UK high street
  const asos = ["asos","topshop","missguided","plt","pretty little thing","boohoo","river island","dorothy perkins","wallis","new look","boden","monsoon","white stuff","fat face","fatface","joules","warehouse","jigsaw","marks & spencer","marks and spencer","primark","laura ashley","sosandar","hobbs"];
  // Zara group
  const zara = ["zara","massimo dutti","mango","pull&bear","pull & bear","bershka","stradivarius","oysho"];
  // Anthropologie / URBN group
  const anthro = ["anthropologie","bhldn","urban outfitters"];

  if (netaporter.some((x) => b.includes(x))) return `https://www.net-a-porter.com/en-us/shop/search?q=${q}`;
  if (ssense.some((x) => b.includes(x))) return `https://www.ssense.com/en-us/search?q=${q}`;
  if (hm.some((x) => b.includes(x))) return `https://www2.hm.com/en_us/search-results.html?q=${nq}`;
  if (uniqlo.some((x) => b.includes(x))) return `https://www.uniqlo.com/us/en/search/?q=${nq}`;
  if (jcrew.some((x) => b.includes(x))) {
    if (b.includes("madewell")) return `https://www.madewell.com/s?q=${nq}`;
    return `https://www.jcrew.com/r/search?q=${nq}`;
  }
  if (gap.some((x) => b.includes(x))) return `https://www.gap.com/browse/search.do?searchText=${q}`;
  if (lulul.some((x) => b.includes(x))) return `https://shop.lululemon.com/search?Ntt=${nq}`;
  if (nike.some((x) => b.includes(x))) return `https://www.nike.com/w?q=${nq}&vst=${nq}`;
  if (adidas.some((x) => b.includes(x))) return `https://www.adidas.com/us/search?q=${nq}`;
  if (target.some((x) => b.includes(x))) return `https://www.target.com/s?searchTerm=${q}`;
  if (everlane.some((x) => b.includes(x))) return `https://www.everlane.com/search?query=${nq}`;
  if (reformation.some((x) => b.includes(x))) return `https://www.thereformation.com/search?q=${nq}`;
  if (abercrombie.some((x) => b.includes(x))) return `https://www.abercrombie.com/shop/us?searchText=${nq}`;
  if (ae.some((x) => b.includes(x))) return `https://www.ae.com/us/en/s/${nq}`;
  if (express_.some((x) => b.includes(x))) return `https://www.express.com/search#text=${nq}`;
  if (anntaylor.some((x) => b.includes(x))) {
    if (b.includes("loft")) return `https://www.loft.com/search/result/index?Ntt=${q}`;
    return `https://www.anntaylor.com/search/searchresult/c/search?refinementValueName=${q}`;
  }
  if (rl.some((x) => b.includes(x))) {
    if (b.includes("tommy")) return `https://usa.tommy.com/en/searchresults?q=${nq}`;
    return `https://www.ralphlauren.com/searchresults?q=${nq}`;
  }
  if (tapestry.some((x) => b.includes(x))) {
    if (b.includes("kate spade")) return `https://www.katespade.com/search?q=${nq}`;
    if (b.includes("coach")) return `https://www.coach.com/search?q=${nq}`;
    return `https://www.michaelkors.com/search#facet=searchText=${nq}`;
  }
  if (toryburch.some((x) => b.includes(x))) return `https://www.toryburch.com/search?q=${nq}`;
  if (pvh.some((x) => b.includes(x))) return `https://www.calvinklein.us/search?q=${nq}`;
  if (ua.some((x) => b.includes(x))) return `https://www.underarmour.com/en-us/searchresults?q=${nq}`;
  if (puma.some((x) => b.includes(x))) return `https://us.puma.com/us/en/search?q=${nq}`;
  if (reebok.some((x) => b.includes(x))) return `https://www.reebok.com/us/search?q=${nq}`;
  if (nb.some((x) => b.includes(x))) return `https://www.newbalance.com/search?q=${nq}`;
  if (vans.some((x) => b.includes(x))) return `https://www.vans.com/en-us/search.html?q=${nq}`;
  if (converse.some((x) => b.includes(x))) return `https://www.converse.com/us/en/search?q=${nq}`;
  if (tnf.some((x) => b.includes(x))) return `https://www.thenorthface.com/search/all?searchTerms=${nq}`;
  if (patagonia.some((x) => b.includes(x))) return `https://www.patagonia.com/search/?q=${nq}`;
  if (alo.some((x) => b.includes(x))) return `https://www.aloyoga.com/search?q=${nq}`;
  if (vuori.some((x) => b.includes(x))) return `https://vuoriclothing.com/search?type=product&q=${nq}`;
  if (revolve.some((x) => b.includes(x))) return `https://www.revolve.com/r/Search.jsp?aliasURL=search%2Fkeyword&navsrc=search&keywords=${q}`;
  if (asos.some((x) => b.includes(x))) return `https://www.asos.com/search/?q=${q}`;
  if (zara.some((x) => b.includes(x))) return `https://www.zara.com/us/en/search?searchTerm=${encodeURIComponent(`${brand} ${name}`)}`;
  if (anthro.some((x) => b.includes(x))) return `https://www.anthropologie.com/search?q=${q}`;
  // Default: rotate across 3 retailers
  const defaults = [
    `https://www.nordstrom.com/sr?keyword=${q}`,
    `https://www.revolve.com/r/Search.jsp?aliasURL=search%2Fkeyword&navsrc=search&keywords=${q}`,
    `https://www.asos.com/search/?q=${q}`,
  ];
  return defaults[index % 3];
}

function shopName(brand: string, index = 0): string {
  const b = brand.toLowerCase();
  if (["the row","celine","loewe","bottega veneta","jacquemus","khaite","toteme","max mara","acne studios","prada","gucci","miu miu","valentino","dior","saint laurent","givenchy","isabel marant","officine générale","nanushka","nili lotan","equipment","a.p.c.","zimmermann","staud","mansur gavriel","veronica beard","l'agence","vince","loro piana","brunello cucinelli","missoni","emilio pucci","alberta ferretti","oscar de la renta","carolina herrera","ulla johnson","saloni","rixo","erdem","roksanda","roland mouret","emilia wickstead","jenny packham","temperley","mother of pearl","raey","shrimps","galvan","proenza schouler","altuzarra","chloé","chloe","stella mccartney","burberry","alexander mcqueen","roberto cavalli","versace","dolce & gabbana","fendi","moschino","etro","paul smith","vivienne westwood","comme des garçons","issey miyake","jil sander","marni","balenciaga","maison margiela","off-white","palm angels","ami paris","anine bing","diane von furstenberg","dvf","alice + olivia","joie","rebecca taylor","ba&sh","faithfull the brand","réalisation par","see by chloé","l.k. bennett","lk bennett"].some((x) => b.includes(x))) return "Net-A-Porter";
  if (["ganni","rag & bone","theory","tibi","rotate","sea new york","sandy liang","frame","doên","by malene birger","iro paris","iro","zadig & voltaire","the kooples","gerard darel","rouje","sézane","sezane","aje","alemais","esse studios","bec & bridge","posse","alice mccall","allsaints","all saints","reiss","whistles","phase eight","mint velvet","ted baker","french connection","karen millen","coast"].some((x) => b.includes(x))) return "SSENSE";
  if (["h&m","h & m","hennes & mauritz","h&m divided","& other stories","other stories","weekday","monki","afound"].some((x) => b.includes(x))) return "H&M";
  if (["uniqlo"].some((x) => b.includes(x))) return "Uniqlo";
  if (b.includes("madewell")) return "Madewell";
  if (["j.crew","j crew","jcrew","crewcuts"].some((x) => b.includes(x))) return "J.Crew";
  if (["gap","banana republic","old navy","athleta","intermix"].some((x) => b.includes(x))) {
    if (b.includes("banana republic")) return "Banana Republic";
    if (b.includes("old navy")) return "Old Navy";
    if (b.includes("athleta")) return "Athleta";
    return "Gap";
  }
  if (["lululemon","lulu lemon","lululemon athletica"].some((x) => b.includes(x))) return "Lululemon";
  if (["nike","jordan brand","air jordan"].some((x) => b.includes(x))) return "Nike";
  if (["adidas","adidas originals","adidas by stella mccartney"].some((x) => b.includes(x))) return "Adidas";
  if (["target","a new day","knox rose","who what wear","universal thread","stars above","colsie","all in motion"].some((x) => b.includes(x))) return "Target";
  if (["everlane"].some((x) => b.includes(x))) return "Everlane";
  if (["reformation"].some((x) => b.includes(x))) return "Reformation";
  if (["abercrombie","hollister","gilly hicks"].some((x) => b.includes(x))) return "Abercrombie";
  if (["american eagle","aerie"].some((x) => b.includes(x))) return b.includes("aerie") ? "Aerie" : "American Eagle";
  if (["express"].some((x) => b.includes(x))) return "Express";
  if (["ann taylor","anntaylor","loft","lou & grey","talbots","j.jill","j jill","chico's","chicos","white house black market","whbm","soma","cabi"].some((x) => b.includes(x))) {
    if (b.includes("loft")) return "LOFT";
    if (b.includes("talbots")) return "Talbots";
    if (b.includes("j.jill") || b.includes("j jill")) return "J.Jill";
    return "Ann Taylor";
  }
  if (["ralph lauren","polo ralph lauren","lauren ralph lauren","double rl","rrl","tommy hilfiger","tommy jeans"].some((x) => b.includes(x))) return b.includes("tommy") ? "Tommy Hilfiger" : "Ralph Lauren";
  if (["michael kors","kate spade","coach","stuart weitzman"].some((x) => b.includes(x))) {
    if (b.includes("kate spade")) return "Kate Spade";
    if (b.includes("coach")) return "Coach";
    return "Michael Kors";
  }
  if (["tory burch","tory sport"].some((x) => b.includes(x))) return "Tory Burch";
  if (["calvin klein","dkny","donna karan"].some((x) => b.includes(x))) return "Calvin Klein";
  if (["under armour","underarmour"].some((x) => b.includes(x))) return "Under Armour";
  if (["puma"].some((x) => b.includes(x))) return "Puma";
  if (["reebok"].some((x) => b.includes(x))) return "Reebok";
  if (["new balance"].some((x) => b.includes(x))) return "New Balance";
  if (["vans"].some((x) => b.includes(x))) return "Vans";
  if (["converse"].some((x) => b.includes(x))) return "Converse";
  if (["the north face","north face"].some((x) => b.includes(x))) return "The North Face";
  if (["patagonia"].some((x) => b.includes(x))) return "Patagonia";
  if (["alo yoga","alo moves"].some((x) => b.includes(x))) return "Alo Yoga";
  if (["vuori"].some((x) => b.includes(x))) return "Vuori";
  if (["revolve","for love & lemons","astr the label","l*space","lovers + friends","free people","show me your mumu","loveshackfancy","love shack fancy","z supply","superdown","princess polly","showpo","lulus","billabong","o'neill","roxy","volcom","bdg"].some((x) => b.includes(x))) return "Revolve";
  if (["asos","topshop","missguided","plt","pretty little thing","boohoo","river island","dorothy perkins","wallis","new look","boden","monsoon","white stuff","fat face","fatface","joules","warehouse","jigsaw","marks & spencer","marks and spencer","primark","laura ashley","sosandar","hobbs"].some((x) => b.includes(x))) return "ASOS";
  if (["zara","massimo dutti","mango","pull&bear","pull & bear","bershka","stradivarius","oysho"].some((x) => b.includes(x))) return "Zara";
  if (["anthropologie","bhldn","urban outfitters"].some((x) => b.includes(x))) return "Anthropologie";
  return ["Nordstrom", "Revolve", "ASOS"][index % 3];
}

async function callGeminiPhotoRecs(query: string, description: string): Promise<PhotoRec[]> {
  const key = import.meta.env.VITE_GEMINI_API_KEY as string | undefined;
  if (!key) return [];
  const prompt = `You are Clem, a fashion finder. The user photographed this exact item:
Search query: "${query}"
Description: "${description}"

Recommend exactly 3 near-identical versions of THIS specific item — same garment type, same silhouette, same colour, same fabric if identifiable. Do NOT suggest complementary pieces or alternatives from a different category. Every recommendation must be a close match to what was photographed.

Return ONLY valid JSON:
{"recs":[{"name":"exact product name as listed on the retailer site","brand":"real brand name","category":"Tops|Bottoms|Dresses|Shoes|Accessories|Outerwear","priceRange":"$X–$Y","why":"one sentence on why this is a near-identical match"}]}`;
  try {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key=${key}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ role: "user", parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.7, maxOutputTokens: 512, responseMimeType: "application/json" },
        }),
      },
    );
    if (!res.ok) return [];
    const json = await res.json() as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> };
    const raw = json.candidates?.[0]?.content?.parts?.[0]?.text ?? "{}";
    const parsed = JSON.parse(raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim()) as { recs?: PhotoRec[] };
    return parsed.recs?.slice(0, 3) ?? [];
  } catch {
    return [];
  }
}

function WishlistPage() {
  const { wishlist, hydrated } = useCloset();
  const { profile } = useProfile();
  const { mode: urlMode } = Route.useSearch();
  const mode = (["wishlist", "discover"].includes(urlMode) ? urlMode : "wishlist") as Mode;
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterBrand, setFilterBrand] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<ScrapedItem[]>([]);

  const wishBrands = useMemo(
    () => [...new Set(wishlist.map((w) => w.brand).filter(Boolean) as string[])],
    [wishlist],
  );
  const filteredWishlist = useMemo(
    () => (filterBrand ? wishlist.filter((w) => w.brand === filterBrand) : wishlist),
    [wishlist, filterBrand],
  );
  const profileChips = useMemo(() => getProfileChips(profile), [profile]);

  const [profileRecs, setProfileRecs] = useState<ScrapedItem[]>([]);
  const [recsLoading, setRecsLoading] = useState(false);

  // Auto-fetch 3 profile-matched recommendations once on mount
  useEffect(() => {
    const q = buildProfileQuery(profile);
    if (!q) return;
    setRecsLoading(true);
    searchProducts({ data: { query: q } })
      .then((r) => setProfileRecs(r.slice(0, 3)))
      .catch(() => {})
      .finally(() => setRecsLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fileRef = useRef<HTMLInputElement>(null);
  const wishImgRef = useRef<HTMLInputElement>(null);
  const [editingWishId, setEditingWishId] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [identifying, setIdentifying] = useState(false);
  const [identifyNote, setIdentifyNote] = useState<string | null>(null);
  const [identifyError, setIdentifyError] = useState<string | null>(null);
  const [photoRecs, setPhotoRecs] = useState<PhotoRec[]>([]);
  const [photoRecsLoading, setPhotoRecsLoading] = useState(false);

  const onAddLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setAdding(true);
    setError(null);
    try {
      const item = await scrapeProduct({ data: { url: url.trim() } });
      closet.addWish(item);
      setUrl("");
    } catch {
      setError("Couldn't fetch that link. Check the URL and try again.");
    } finally {
      setAdding(false);
    }
  };

  const onSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    await runSearch(query.trim());
  };

  const runSearch = async (q: string) => {
    setQuery(q);
    setResults([]);
    setPhotoRecs([]);
    setImagePreview(null);
    setIdentifyNote(null);
    setIdentifyError(null);
    setPhotoRecsLoading(true);
    try {
      const recs = await callGeminiPhotoRecs(q, q);
      setPhotoRecs(recs);
    } catch {
      setPhotoRecs([]);
    } finally {
      setPhotoRecsLoading(false);
    }
  };

  const onPickImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 6 * 1024 * 1024) {
      setIdentifyError("Image too large — please use one under 6 MB.");
      return;
    }
    setIdentifyError(null);
    setIdentifyNote(null);
    setPhotoRecs([]);
    setResults([]);
    setIdentifying(true);

    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result as string);
        r.onerror = () => reject(new Error("read failed"));
        r.readAsDataURL(file);
      });
      setImagePreview(dataUrl);

      const { query: q, description } = await identifyFromImage({ data: { image: dataUrl } });
      setIdentifyNote(description || q);
      setIdentifying(false);

      setPhotoRecsLoading(true);
      const recs = await callGeminiPhotoRecs(q, description || q);
      setPhotoRecs(recs);
    } catch (err) {
      setIdentifyError(err instanceof Error ? err.message : "Couldn't identify that image.");
    } finally {
      setIdentifying(false);
      setPhotoRecsLoading(false);
    }
  };

  const heart = (item: ScrapedItem) => {
    if (closet.hasWishUrl(item.url)) return;
    closet.addWish(item);
  };

  const onWishImagePick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !editingWishId) return;
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result as string);
      r.onerror = () => reject(new Error("read failed"));
      r.readAsDataURL(file);
    });
    closet.updateWish(editingWishId, { image: dataUrl });
    setEditingWishId(null);
  };

  return (
    <PageShell title="Wishlist">
      <section className="px-6 pt-4 pb-10">
        <div className="flex gap-2 mb-5 border border-ink/20 rounded-full p-1">
          <Link
            to="/wishlist"
            search={{ mode: "wishlist" }}
            className={`flex-1 rounded-full py-2 text-xs font-medium uppercase tracking-[0.18em] transition text-center ${
              mode === "wishlist" ? "bg-mauve text-cream" : "text-ink/60"
            }`}
          >
            {`Wishlist${wishlist?.length ? ` · ${wishlist.length}` : ""}`}
          </Link>
          <Link
            to="/wishlist"
            search={{ mode: "discover" }}
            className={`flex-1 rounded-full py-2 text-xs font-medium uppercase tracking-[0.18em] transition text-center ${
              mode === "discover" ? "bg-mauve text-cream" : "text-ink/60"
            }`}
          >
            Discover
          </Link>
          <Link
            to="/before-you-buy"
            className="flex-1 rounded-full py-2 text-xs font-medium uppercase tracking-[0.18em] transition text-center text-ink/60"
          >
            Before you buy
          </Link>
        </div>




        <input
          ref={wishImgRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={onWishImagePick}
        />

        {mode === "wishlist" ? (
          <>
            <form onSubmit={onAddLink} className="flex gap-2 mb-5">
              <div className="flex-1 relative">
                <Link2 className="size-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="Paste a product link"
                  className="w-full rounded-full bg-card border border-border pl-9 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-mint/30"
                />
              </div>
              <button
                type="submit"
                disabled={adding || !url.trim()}
                className="rounded-full bg-mauve text-cream px-4 text-xs font-medium active:scale-95 transition inline-flex items-center gap-1.5 disabled:opacity-40"
              >
                {adding ? <Loader2 className="size-3.5 animate-spin" /> : <Heart className="size-3.5" />}
                Save
              </button>
            </form>
            {error && <p className="text-xs text-destructive mb-3">{error}</p>}

            {wishBrands.length > 1 && (
              <div className="flex gap-2 overflow-x-auto pb-1 -mx-6 px-6 mb-4 snap-x">
                <button
                  type="button"
                  onClick={() => setFilterBrand(null)}
                  className={`flex-none snap-start rounded-full px-3 py-1.5 text-[10px] uppercase tracking-[0.18em] border transition ${!filterBrand ? "bg-mauve text-cream border-mauve" : "border-border text-muted-foreground"}`}
                >
                  All
                </button>
                {wishBrands.map((b) => (
                  <button
                    key={b}
                    type="button"
                    onClick={() => setFilterBrand(filterBrand === b ? null : b)}
                    className={`flex-none snap-start rounded-full px-3 py-1.5 text-[10px] uppercase tracking-[0.18em] border transition ${filterBrand === b ? "bg-mauve text-cream border-mauve" : "border-border text-muted-foreground"}`}
                  >
                    {b}
                  </button>
                ))}
              </div>
            )}

            {hydrated && wishlist.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-border rounded-2xl">
                <Heart className="size-6 mx-auto mb-2 opacity-40" strokeWidth={1.5} />
                <p className="text-sm font-serif tracking-[0.04em] uppercase">Nothing saved yet</p>
                <p className="text-[11px] text-muted-foreground mt-1">Paste a link or try Discover.</p>
              </div>
            ) : filteredWishlist.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground">
                <p className="text-xs">No saved items from {filterBrand}.</p>
              </div>
            ) : (
              <ul className="grid grid-cols-2 gap-3">
                {filteredWishlist.map((w) => (
                  <li key={w.id} className="rounded-2xl overflow-hidden bg-card border border-border">
                    <div className="aspect-[3/4] bg-mint-soft/30 overflow-hidden relative">
                      {w.image ? (
                        <WishImg src={w.image} alt={w.title} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full grid place-items-center text-muted-foreground">
                          <Heart className="size-6 opacity-40" />
                        </div>
                      )}
                      <button
                        onClick={() => closet.removeWish(w.id)}
                        aria-label="Remove"
                        className="absolute top-2 right-2 size-7 grid place-items-center rounded-full bg-background/80 backdrop-blur"
                      >
                        <X className="size-3.5" />
                      </button>
                      <button
                        onClick={() => { setEditingWishId(w.id); wishImgRef.current?.click(); }}
                        aria-label="Change image"
                        className="absolute bottom-2 right-2 size-7 grid place-items-center rounded-full bg-background/80 backdrop-blur"
                      >
                        <Camera className="size-3.5" />
                      </button>
                      {w.price && (
                        <span className="absolute bottom-2 left-2 text-[10px] bg-background/85 backdrop-blur px-2 py-0.5 rounded-full text-foreground/80">
                          {w.price}
                        </span>
                      )}
                    </div>
                    <div className="p-3">
                      {w.brand && <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{w.brand}</p>}
                      <a href={w.url} target="_blank" rel="noreferrer" className="block text-xs leading-tight line-clamp-2 mt-0.5 hover:underline">
                        {w.title}
                      </a>
                      <div className="flex gap-2 mt-2.5">
                        <button
                          onClick={() => closet.promoteWishToCloset(w.id)}
                          className="flex-1 rounded-full bg-mauve text-cream py-1.5 text-[10px] font-medium uppercase tracking-wider active:scale-95 transition inline-flex items-center justify-center gap-1"
                        >
                          <ShirtIcon className="size-3" /> To closet
                        </button>
                        <a
                          href={w.url}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full bg-mint-soft/50 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider active:scale-95 transition inline-flex items-center gap-1"
                        >
                          <ExternalLink className="size-3" /> Shop
                        </a>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <>
            {/* Profile-based recommendations */}
            {(recsLoading || profileRecs.length > 0) && (
              <div className="mb-6">
                <p className="text-[10px] uppercase tracking-[0.22em] text-mint mb-0.5">Picked for you</p>
                <p className="text-[10px] text-muted-foreground mb-3">Based on your style profile</p>
                {recsLoading ? (
                  <div className="flex items-center gap-2 py-4 text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    <span className="text-xs">Finding pieces for your style…</span>
                  </div>
                ) : (
                  <ul className="space-y-2.5">
                    {profileRecs.map((r) => {
                      const saved = closet.hasWishUrl(r.url);
                      return (
                        <li key={r.url} className="flex gap-3 p-3 rounded-2xl bg-card border border-border">
                          <a href={r.url} target="_blank" rel="noreferrer" className="size-16 shrink-0 rounded-xl overflow-hidden bg-mint-soft/30 grid place-items-center">
                            {r.image ? (
                              <WishImg src={r.image} alt="" className="w-full h-full object-cover" />
                            ) : (
                              <Heart className="size-4 opacity-40" />
                            )}
                          </a>
                          <div className="flex-1 min-w-0">
                            {r.brand && <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{r.brand}</p>}
                            <a href={r.url} target="_blank" rel="noreferrer" className="block text-xs leading-tight line-clamp-2 hover:underline">{r.title}</a>
                            <div className="flex items-center gap-2 mt-2">
                              <button
                                onClick={() => heart(r)}
                                disabled={saved}
                                className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-[10px] font-medium uppercase tracking-wider transition ${saved ? "bg-mint/20 text-mint" : "bg-mauve text-cream active:scale-95"}`}
                              >
                                <Heart className={`size-3 ${saved ? "fill-current" : ""}`} />
                                {saved ? "Saved" : "Heart"}
                              </button>
                              <a href={r.url} target="_blank" rel="noreferrer" className="text-[10px] text-muted-foreground inline-flex items-center gap-1 hover:text-foreground transition">
                                <ExternalLink className="size-3" /> Shop
                              </a>
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}

            <div className="mb-5">
              <h2 className="text-xl font-serif tracking-[0.04em] text-ink">Saw something you love?</h2>
              <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
                Search the web, paste a link, or upload a screenshot — Clem will find it or a close dupe.
              </p>
            </div>
            <form onSubmit={onSearch} className="flex gap-2 mb-5">
              <div className="flex-1 relative">
                <Search className="size-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search the web — “linen blazer cream”"
                  className="w-full rounded-full bg-card border border-border pl-9 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-mint/30"
                />
              </div>
              <button
                type="submit"
                disabled={photoRecsLoading || query.trim().length < 2}
                className="rounded-full bg-mauve text-cream px-4 text-xs font-medium active:scale-95 transition inline-flex items-center gap-1.5 disabled:opacity-40"
              >
                {photoRecsLoading && !identifying ? <Loader2 className="size-3.5 animate-spin" /> : "Search"}
              </button>
            </form>

            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onPickImage}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={identifying}
              className="w-full mb-5 rounded-2xl border border-dashed border-ink/30 bg-cream/40 py-3 px-4 text-left flex items-center gap-3 active:scale-[0.99] transition disabled:opacity-60"
            >
              <span className="size-9 grid place-items-center rounded-full bg-mauve text-cream shrink-0">
                {identifying ? <Loader2 className="size-4 animate-spin" /> : <Camera className="size-4" />}
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-xs font-medium uppercase tracking-[0.18em] text-ink inline-flex items-center gap-1.5">
                  <Sparkles className="size-3" /> Find it from a photo
                </span>
                <span className="block text-[11px] text-ink/60 mt-0.5">
                  {identifying
                    ? "Reading the image…"
                    : "Upload a screenshot — Clem will hunt down the piece or close dupes."}
                </span>
              </span>
              {imagePreview && (
                <img
                  src={imagePreview}
                  alt=""
                  className="size-12 rounded-lg object-cover shrink-0"
                />
              )}
            </button>

            {identifyNote && !identifying && (
              <p className="-mt-3 mb-4 text-[11px] text-ink/70 italic">
                Identified: {identifyNote}
              </p>
            )}
            {identifyError && (
              <p className="-mt-3 mb-4 text-[11px] text-destructive">{identifyError}</p>
            )}

            {(photoRecsLoading || photoRecs.length > 0) && (
              <div className="mb-5">
                <p className="text-[10px] uppercase tracking-[0.22em] text-mint mb-1">
                  {photoRecsLoading ? "Curating options…" : "Shop similar"}
                </p>
                {photoRecsLoading && (
                  <p className="text-[10px] text-muted-foreground mb-3">Finding the closest matches…</p>
                )}
                <div className="flex gap-3 overflow-x-auto pb-2 -mx-6 px-6 snap-x snap-mandatory no-scrollbar">
                  {photoRecsLoading
                    ? [0, 1, 2].map((i) => (
                        <div key={i} className="flex-none w-44 h-48 rounded-2xl bg-card border border-border animate-pulse snap-start" />
                      ))
                    : photoRecs.map((rec, i) => (
                        <a
                          key={i}
                          href={shopUrl(rec.brand, rec.name, i)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex-none w-44 snap-start rounded-2xl border border-border bg-card p-4 flex flex-col gap-2 active:scale-95 transition"
                        >
                          <span className="text-[9px] uppercase tracking-[0.2em] text-mint">{rec.category}</span>
                          <div>
                            <p className="text-xs font-medium text-foreground leading-snug">{rec.name}</p>
                            <p className="text-[10px] text-muted-foreground mt-0.5">{rec.brand}</p>
                          </div>
                          <p className="text-[10px] font-serif italic text-ink/70 leading-snug flex-1">{rec.why}</p>
                          <div className="flex items-center justify-between mt-auto pt-2 border-t border-border/40">
                            <span className="text-[10px] text-foreground/70">{rec.priceRange}</span>
                            <span className="inline-flex items-center gap-0.5 text-[10px] uppercase tracking-[0.18em] text-mint">
                              {shopName(rec.brand, i)} <ArrowUpRight className="size-3" strokeWidth={1.5} />
                            </span>
                          </div>
                        </a>
                      ))}
                </div>
              </div>
            )}


            {!searching && results.length === 0 && photoRecs.length === 0 && !photoRecsLoading && (
              <div className="py-6">
                {profileChips.length > 0 ? (
                  <>
                    <p className="text-[10px] uppercase tracking-[0.22em] text-mint mb-1">Try searching</p>
                    <p className="text-[10px] text-muted-foreground mb-3">Based on your style profile</p>
                    <div className="flex flex-wrap gap-2">
                      {profileChips.map((chip) => (
                        <button
                          key={chip}
                          type="button"
                          onClick={() => runSearch(chip)}
                          className="text-[11px] tracking-[0.04em] px-3 py-1.5 rounded-full border border-mauve/40 text-foreground bg-mauve/5 hover:bg-mauve/15 transition"
                        >
                          {chip}
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="text-center py-10 border border-dashed border-border rounded-2xl">
                    <Search className="size-6 mx-auto mb-2 opacity-40" strokeWidth={1.5} />
                    <p className="text-sm font-serif tracking-[0.04em] uppercase">Search any piece</p>
                    <p className="text-[11px] text-muted-foreground mt-1">Tap the heart on a result to save it.</p>
                  </div>
                )}
              </div>
            )}

            {results.length > 0 && (
              <>
                <p className="text-[10px] uppercase tracking-[0.22em] text-mint mb-3">Results</p>
                <ul className="grid grid-cols-3 gap-2.5">
                  {results.map((r) => {
                    const saved = closet.hasWishUrl(r.url);
                    return (
                      <li key={r.url} className="rounded-2xl overflow-hidden bg-card border border-border flex flex-col">
                        <a href={r.url} target="_blank" rel="noreferrer" className="aspect-[3/4] bg-mint-soft/30 overflow-hidden grid place-items-center">
                          {r.image ? (
                            <WishImg src={r.image} alt={r.title} className="w-full h-full object-cover" />
                          ) : (
                            <Heart className="size-5 opacity-40" />
                          )}
                        </a>
                        <div className="p-2 flex flex-col flex-1 gap-1.5">
                          {r.brand && <p className="text-[9px] uppercase tracking-wider text-muted-foreground leading-none">{r.brand}</p>}
                          <a href={r.url} target="_blank" rel="noreferrer" className="text-[10px] leading-tight line-clamp-2 hover:underline flex-1">{r.title}</a>
                          <div className="flex gap-1.5 mt-auto">
                            <button
                              onClick={() => heart(r)}
                              disabled={saved}
                              aria-label={saved ? "Saved" : "Save"}
                              className={`flex-1 rounded-full py-1 text-[9px] font-medium uppercase tracking-wider transition inline-flex items-center justify-center gap-0.5 ${
                                saved ? "bg-mint/20 text-mint" : "bg-mauve text-cream active:scale-95"
                              }`}
                            >
                              <Heart className={`size-2.5 ${saved ? "fill-current" : ""}`} />
                              {saved ? "Saved" : "Save"}
                            </button>
                            <a
                              href={r.url}
                              target="_blank"
                              rel="noreferrer"
                              aria-label="Shop"
                              className="rounded-full bg-mint-soft/50 px-2 py-1 text-[9px] font-medium uppercase tracking-wider inline-flex items-center gap-0.5"
                            >
                              <ExternalLink className="size-2.5" />
                            </a>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </>
        )}

        <div className="mt-8 p-4 rounded-2xl bg-mint-soft/30 border border-border">
          <p className="text-[10px] uppercase tracking-[0.18em] text-mint mb-1">Coming soon</p>
          <p className="text-xs leading-relaxed">
            A Clem browser extension so you can heart pieces straight from any retailer.{" "}
            <Link to="/profile" className="underline">Read the roadmap →</Link>
          </p>
        </div>
      </section>
    </PageShell>
  );
}
