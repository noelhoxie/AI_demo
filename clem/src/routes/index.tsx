import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { toast } from "sonner";
import { PageShell } from "@/components/vesti/PageShell";
import { useCloset, closet, CATEGORIES, SEASONS, itemStatus, type Category, type Season, type Item, type ItemStatus, type DepartingIntent } from "@/lib/vesti/store";
import { Archive, Bookmark, Check, ChevronDown, FolderPlus, Heart, Pencil, Search, Share2, Shirt, SlidersHorizontal, Sparkles, SunMoon, Tag, X, Zap } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LogWearSheet } from "@/components/vesti/LogWearSheet";
import { shouldAutoOpenMorning, markMorningSeenToday } from "@/lib/vesti/morning";
import { getLoanForItem, matchesLendingFilter, formatDueDate, type LendingFilter } from "@/lib/vesti/lending";


export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Your Wardrobe — Clem" },
      { name: "description", content: "Browse and organize your digital wardrobe." },
      { property: "og:title", content: "Your Wardrobe — Clem" },
      { property: "og:description", content: "Browse and organize your digital wardrobe." },
    ],
  }),
  component: ClosetHome,
});

function tripDays(start?: string, end?: string): string[] {
  if (!start || !end) return [];
  const out: string[] = [];
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  for (let d = new Date(s); d <= e; d.setDate(d.getDate() + 1)) {
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

function ClosetHome() {


  const { items, folders } = useCloset();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState<Category | "all">("all");
  const [sea, setSea] = useState<Season | "all">("all");
  const [color, setColor] = useState<string>("all");
  const [lend, setLend] = useState<LendingFilter>("all");
  const [tagging, setTagging] = useState<Item | null>(null);
  const [newFolder, setNewFolder] = useState("");
const [logOpen, setLogOpen] = useState(false);
  const [tab, setTab] = useState<ItemStatus>("active");
  const [vaultPrompt, setVaultPrompt] = useState<Item | null>(null);
  const [vaultStory, setVaultStory] = useState("");
  const [vaultOccasion, setVaultOccasion] = useState("");
  const [vaultPerson, setVaultPerson] = useState("");
  const [departingPrompt, setDepartingPrompt] = useState<Item | null>(null);
  const [departIntent, setDepartIntent] = useState<DepartingIntent>("sell");
  const [departNotes, setDepartNotes] = useState("");
  const [departListed, setDepartListed] = useState(false);
  const [showMorningBanner, setShowMorningBanner] = useState(false);
  const [detailItem, setDetailItem] = useState<Item | null>(null);
  const [filterSheetOpen, setFilterSheetOpen] = useState(false);
  


  

  // Multi-select state
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  
  const longPressTimer = useRef<number | null>(null);
  const longPressedRef = useRef(false);

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelected(new Set());
  };

  // Exit select mode when the user changes tabs.
  useEffect(() => { exitSelectMode(); }, [tab]);

  const onCardPointerDown = (id: string) => {
    longPressedRef.current = false;
    if (longPressTimer.current) window.clearTimeout(longPressTimer.current);
    longPressTimer.current = window.setTimeout(() => {
      longPressedRef.current = true;
      setSelectMode(true);
      setSelected((s) => {
        const next = new Set(s);
        next.add(id);
        return next;
      });
    }, 450);
  };
  const cancelLongPress = () => {
    if (longPressTimer.current) {
      window.clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };
  const onCardClick = (id: string, e: React.MouseEvent) => {
    if (longPressedRef.current) {
      e.preventDefault();
      e.stopPropagation();
      longPressedRef.current = false;
      return;
    }
    if (selectMode) {
      e.preventDefault();
      setSelected((s) => {
        const next = new Set(s);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      return;
    }
    const it = items.find((x) => x.id === id);
    if (it) setDetailItem(it);
  };

  useEffect(() => {
    // Soft nudge instead of a redirect — power users tap the sun icon anytime.
    if (shouldAutoOpenMorning()) {
      setShowMorningBanner(true);
    }
  }, []);

  const dismissMorningBanner = () => {
    markMorningSeenToday();
    setShowMorningBanner(false);
  };


  const colors = useMemo(() => {
    const set = new Set<string>();
    items.forEach((i) => i.color && set.add(i.color));
    return Array.from(set).sort();
  }, [items]);

  const tabItems = useMemo(
    () => items.filter((i) => itemStatus(i) === tab),
    [items, tab],
  );

  const counts = useMemo(() => {
    const c = { active: 0, archived: 0, departing: 0, vault: 0 } as Record<ItemStatus, number>;
    items.forEach((i) => { c[itemStatus(i)] += 1; });
    return c;
  }, [items]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tabItems.filter((i) => {
      const catOk = cat === "all" || i.category === cat;
      const seaOk = sea === "all" || i.season === sea;
      const colOk = color === "all" || i.color === color;
      const lendOk = matchesLendingFilter(i.id, lend);
      const memoryText = i.memory
        ? `${i.memory.story ?? ""} ${i.memory.occasion ?? ""} ${i.memory.person ?? ""}`
        : "";
      const text = `${i.name} ${i.brand ?? ""} ${i.color ?? ""} ${i.category} ${i.season} ${memoryText}`.toLowerCase();
      const qOk = q.length === 0 || text.includes(q);
      return catOk && seaOk && colOk && lendOk && qOk;
    });
  }, [tabItems, query, cat, sea, color, lend]);

  const activeFilters = (cat !== "all" ? 1 : 0) + (sea !== "all" ? 1 : 0) + (color !== "all" ? 1 : 0) + (lend !== "all" ? 1 : 0) + (query ? 1 : 0);

  const isVault = tab === "vault";
  const isDeparting = tab === "departing";

  const STATUS_LABELS: Record<ItemStatus, string> = {
    active: "Active",
    archived: "Archived",
    departing: "Departing",
    vault: "Memory Vault",
  };

  // Apply a status change to one or more items and show a 5-second Undo toast.
  // Snapshots full prior state (status + memory + departing) so revert is exact.
  const moveWithUndo = (
    ids: string[],
    to: ItemStatus,
    opts?: { memory?: Item["memory"]; departing?: Item["departing"] },
  ) => {
    if (ids.length === 0) return;
    const idSet = new Set(ids);
    const snap = items
      .filter((i) => idSet.has(i.id))
      .map((i) => ({ id: i.id, status: i.status ?? "active", memory: i.memory, departing: i.departing }));
    ids.forEach((id) => closet.setItemStatus(id, to, opts));
    const noun = ids.length === 1 ? "piece" : `${ids.length} pieces`;
    toast(`Moved ${noun} to ${STATUS_LABELS[to]}`, {
      duration: 5000,
      action: {
        label: "Undo",
        onClick: () => {
          snap.forEach((p) =>
            closet.setItemStatus(p.id, p.status, { memory: p.memory, departing: p.departing }),
          );
          toast.success("Reverted");
        },
      },
    });
  };

  const handleMove = (item: Item, to: ItemStatus) => {
    if (to === "vault") {
      setVaultStory(item.memory?.story ?? "");
      setVaultOccasion(item.memory?.occasion ?? "");
      setVaultPerson(item.memory?.person ?? "");
      setVaultPrompt(item);
      return;
    }
    if (to === "departing") {
      setDepartIntent(item.departing?.intent ?? "sell");
      setDepartNotes(item.departing?.notes ?? "");
      setDepartListed(item.departing?.listed ?? false);
      setDepartingPrompt(item);
      return;
    }
    moveWithUndo([item.id], to);
  };

  const bulkMove = (to: ItemStatus) => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    // Bulk moves to vault/departing skip the form prompts — defaults applied,
    // users can edit each piece's details afterward.
    if (to === "vault") {
      moveWithUndo(ids, "vault", { memory: { story: "" } });
    } else if (to === "departing") {
      moveWithUndo(ids, "departing", { departing: { intent: "sell" } });
    } else {
      moveWithUndo(ids, to);
    }
    exitSelectMode();
  };

  const saveVaultMemory = () => {
    if (!vaultPrompt) return;
    moveWithUndo([vaultPrompt.id], "vault", {
      memory: {
        story: vaultStory.trim(),
        occasion: vaultOccasion.trim() || undefined,
        person: vaultPerson.trim() || undefined,
      },
    });
    setVaultPrompt(null);
    setVaultStory("");
    setVaultOccasion("");
    setVaultPerson("");
  };

  const saveDeparting = () => {
    if (!departingPrompt) return;
    moveWithUndo([departingPrompt.id], "departing", {
      departing: {
        intent: departIntent,
        listed: departIntent === "sell" ? departListed : undefined,
        notes: departNotes.trim() || undefined,
      },
    });
    setDepartingPrompt(null);
    setDepartNotes("");
    setDepartListed(false);
  };

  const allSelected = visible.length > 0 && visible.every((i) => selected.has(i.id));
  const toggleSelectAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(visible.map((i) => i.id)));
    }
  };

  return (
    <PageShell title="Your Wardrobe">
      <div style={isVault ? { backgroundColor: "#EDE5DC" } : undefined} className="transition-colors">
      {showMorningBanner && (
        <div className="mx-8 mt-6 border border-ink/15 bg-cream/60 backdrop-blur-sm px-4 py-3 flex items-center gap-3">
          <SunMoon className="size-4 text-mauve shrink-0" strokeWidth={1.25} />
          <p className="flex-1 text-[12px] font-serif italic text-ink/80 leading-snug">
            Good morning — your look for today is ready.
          </p>
          <Link
            to="/morning"
            onClick={dismissMorningBanner}
            className="text-[10px] uppercase tracking-[0.22em] text-ink hover:text-mauve transition"
          >
            See it →
          </Link>
          <button
            type="button"
            onClick={dismissMorningBanner}
            aria-label="Dismiss"
            className="size-6 grid place-items-center text-ink/50 hover:text-ink transition"
          >
            <X className="size-3.5" strokeWidth={1.5} />
          </button>
        </div>
      )}
      {/* Editorial intro */}
      <section className="px-8 pt-10 pb-2">
        <h2 className="font-serif text-[27px] leading-[1.1] tracking-[0.06em] text-ink uppercase">
          YOUR WARDROBE
        </h2>
        <p className="text-xs text-mauve mt-4 tracking-wide">
          {visible.length} of {counts[tab]} {tab === "vault" ? "kept piece" : tab === "archived" ? "archived piece" : tab === "departing" ? "departing piece" : "active piece"}{counts[tab] !== 1 ? "s" : ""}
          {activeFilters > 0 && " · filtered"}
        </p>
        {!isVault && !isDeparting && (
          <button
            type="button"
            onClick={() => setLogOpen(true)}
            className="mt-5 inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] border border-ink/30 px-4 py-2 hover:bg-ink hover:text-cream transition"
          >
            <Shirt className="size-3" strokeWidth={1.5} />
            Log today's outfit
          </button>
        )}
        {isDeparting && counts.departing > 0 && (
          <button
            type="button"
            onClick={async () => {
              const url = `${window.location.origin}/share/departing`;
              const shareData = {
                title: "Departing pieces — Clem",
                text: "First dibs on what I'm parting with.",
                url,
              };
              try {
                if (navigator.share) await navigator.share(shareData);
                else {
                  await navigator.clipboard.writeText(url);
                  alert("Link copied to clipboard");
                }
              } catch {
                /* user cancelled */
              }
            }}
            className="mt-5 inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] border border-ink/30 px-4 py-2 hover:bg-ink hover:text-cream transition"
          >
            <Share2 className="size-3" strokeWidth={1.5} />
            Share departing
          </button>
        )}
      </section>

      {/* Status filter — single dropdown pill */}
      <section className="px-8 pt-8">
        {(() => {
          const TABS = [
            { id: "active" as const, label: "Active", icon: Sparkles },
            { id: "archived" as const, label: "Archived", icon: Archive },
            { id: "departing" as const, label: "Departing", icon: Tag },
            { id: "vault" as const, label: "Memory Vault", icon: Heart },
          ];
          const current = TABS.find((t) => t.id === tab)!;
          const CurrentIcon = current.icon;
          return (
            <DropdownMenu>
              <DropdownMenuTrigger className="inline-flex items-center gap-2 border-b border-ink/30 hover:border-ink pb-2 text-[11px] uppercase tracking-[0.22em] text-ink transition focus:outline-none">
                <CurrentIcon className="size-3" strokeWidth={1.5} />
                {current.label}
                <span className="text-[9px] tracking-normal text-mauve">{counts[current.id]}</span>
                <ChevronDown className="size-3 text-ink/50" strokeWidth={1.5} />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="min-w-[180px] rounded-none border-ink/20">
                {TABS.map(({ id, label, icon: Icon }) => (
                  <DropdownMenuItem
                    key={id}
                    onSelect={() => setTab(id)}
                    className="rounded-none text-[11px] uppercase tracking-[0.18em] py-2"
                  >
                    <Icon className="size-3" strokeWidth={1.5} />
                    <span className="flex-1">{label}</span>
                    <span className="text-[9px] text-mauve">{counts[id]}</span>
                    {tab === id && <Check className="size-3 text-ink" strokeWidth={1.5} />}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          );
        })()}
      </section>


      <section className="px-8 pt-8">
        <p className="font-serif italic text-base text-ink/70 leading-snug">
          {tab === "vault"
            ? "Some pieces are kept for what they meant, not what they match."
            : tab === "archived"
              ? "Resting pieces — off-season, between sizes, or simply on pause."
              : tab === "departing"
                ? "On their way out — pieces to sell, give, or donate before they leave the closet."
                : "The pieces in rotation right now — your daily wardrobe at a glance."}
        </p>
      </section>

      {/* Search */}
      <section className="px-8 pt-8">
        <div className="relative border-b border-taupe">
          <Search className="size-4 text-mauve/70 absolute left-0 top-1/2 -translate-y-1/2" strokeWidth={1.25} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={isVault ? "Search by name, story, occasion, or person" : "Search the wardrobe"}
            className="w-full bg-transparent pl-7 pr-8 py-3 text-sm tracking-wide placeholder:text-muted-foreground/70 focus:outline-none"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-0 top-1/2 -translate-y-1/2 text-muted-foreground p-1"
              aria-label="Clear search"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>
      </section>

      {/* Filters trigger */}
      {!isVault && (
        <section className="px-8 pt-5">
          {(() => {
            const filterChipCount = (cat !== "all" ? 1 : 0) + (sea !== "all" ? 1 : 0) + (color !== "all" ? 1 : 0) + (lend !== "all" ? 1 : 0);
            return (
              <button
                type="button"
                onClick={() => setFilterSheetOpen(true)}
                className="relative inline-flex items-center gap-2 border border-ink/30 px-4 py-2 text-[10px] uppercase tracking-[0.22em] text-ink hover:bg-ink hover:text-cream transition"
              >
                <SlidersHorizontal className="size-3" strokeWidth={1.5} />
                Filters
                {filterChipCount > 0 && (
                  <span className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 bg-ink text-cream text-[9px] tracking-normal rounded-full">
                    {filterChipCount}
                  </span>
                )}
              </button>
            );
          })()}
        </section>
      )}

      <Sheet open={filterSheetOpen} onOpenChange={setFilterSheetOpen}>
        <SheetContent side="bottom" className="bg-cream border-ink/15 rounded-t-2xl max-h-[85vh] overflow-y-auto">
          <SheetHeader className="text-left">
            <SheetTitle className="font-serif text-xl tracking-[0.04em] uppercase text-ink">Filters</SheetTitle>
            <SheetDescription className="text-xs text-mauve tracking-wide">
              Refine your wardrobe by category, season, color, or lending status.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-6 grid grid-cols-2 gap-x-5 gap-y-5">
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-[#6B3A4A] mb-2">Category</p>
              <Select value={cat} onValueChange={(v) => setCat(v as Category | "all")}>
                <SelectTrigger className="rounded-none border-0 border-b border-ink/30 bg-transparent px-0 h-9 text-[11px] uppercase tracking-[0.18em] text-ink shadow-none focus:ring-0 hover:border-ink transition">
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-[#6B3A4A] mb-2">Season</p>
              <Select value={sea} onValueChange={(v) => setSea(v as Season | "all")}>
                <SelectTrigger className="rounded-none border-0 border-b border-ink/30 bg-transparent px-0 h-9 text-[11px] uppercase tracking-[0.18em] text-ink shadow-none focus:ring-0 hover:border-ink transition">
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  {SEASONS.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-[#6B3A4A] mb-2">Color</p>
              <Select value={color} onValueChange={setColor}>
                <SelectTrigger className="rounded-none border-0 border-b border-ink/30 bg-transparent px-0 h-9 text-[11px] uppercase tracking-[0.18em] text-ink shadow-none focus:ring-0 hover:border-ink transition">
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  {colors.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-[#6B3A4A] mb-2">Lending</p>
              <Select value={lend} onValueChange={(v) => setLend(v as LendingFilter)}>
                <SelectTrigger className="rounded-none border-0 border-b border-ink/30 bg-transparent px-0 h-9 text-[11px] uppercase tracking-[0.18em] text-ink shadow-none focus:ring-0 hover:border-ink transition">
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="available">Available to Lend</SelectItem>
                  <SelectItem value="lent">Currently Lent Out</SelectItem>
                  <SelectItem value="not-lendable">Not Lendable</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {(cat !== "all" || sea !== "all" || color !== "all" || lend !== "all") && (
            <button
              type="button"
              onClick={() => {
                setCat("all");
                setSea("all");
                setColor("all");
                setLend("all");
              }}
              className="mt-6 text-[10px] uppercase tracking-[0.22em] text-ink/60 italic underline underline-offset-4 decoration-ink/30"
            >
              Clear filters
            </button>
          )}
          <div className="mt-8 flex justify-end">
            <button
              type="button"
              onClick={() => setFilterSheetOpen(false)}
              className="inline-flex items-center gap-2 bg-ink text-cream px-5 py-2 text-[10px] uppercase tracking-[0.22em] hover:bg-ink/85 transition"
            >
              Done
            </button>
          </div>
        </SheetContent>
      </Sheet>




      {/* Gallery */}
      <section className="px-8 pt-12 pb-16">
        {!selectMode && visible.length > 0 && (
          <p className="text-[10px] uppercase tracking-[0.22em] text-mauve/70 italic text-center mb-8">
            Hold any piece to organize
          </p>
        )}
        {visible.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            {isVault ? (
              <>
                <p className="font-serif italic text-2xl mb-2 tracking-[0.02em]">Nothing kept here yet</p>
                <p className="text-xs tracking-wide">Move a piece to the Memory Vault from its menu.</p>
              </>
            ) : tab === "archived" && counts.archived === 0 ? (
              <>
                <p className="font-serif text-2xl mb-2 tracking-[0.06em] uppercase">Nothing archived</p>
                <p className="text-xs tracking-wide">Pieces you pause will live here.</p>
              </>
            ) : tab === "departing" && counts.departing === 0 ? (
              <>
                <p className="font-serif text-2xl mb-2 tracking-[0.06em] uppercase">Nothing departing</p>
                <p className="text-xs tracking-wide">Pieces you're selling, giving, or donating will gather here.</p>
              </>
            ) : (
              <>
                <p className="font-serif text-2xl mb-2 tracking-[0.06em] uppercase">Nothing matches</p>
                <p className="text-xs tracking-wide">Try clearing filters or another search.</p>
              </>
            )}
          </div>
        ) : isVault ? (
          <div className="flex flex-col gap-10">
            {visible.map((item, i) => {
              const isSel = selected.has(item.id);
              return (
              <article
                key={item.id}
                className={`animate-rise ${selectMode ? "cursor-pointer select-none" : ""}`}
                style={{ animationDelay: `${i * 40}ms` }}
                onPointerDown={() => onCardPointerDown(item.id)}
                onPointerUp={cancelLongPress}
                onPointerLeave={cancelLongPress}
                onPointerCancel={cancelLongPress}
                onClick={(e) => onCardClick(item.id, e)}
              >
                <div className={`relative w-full aspect-[4/5] bg-card mb-5 overflow-hidden shadow-[0_18px_36px_-22px_rgba(68,50,35,0.32)] transition ${
                  selectMode && isSel ? "ring-2 ring-ink ring-offset-2 ring-offset-cream" : ""
                }`}>
                  <img
                    src={item.image}
                    alt={item.name}
                    loading="lazy"
                    className="w-full h-full object-cover"
                  />
                  {selectMode && (
                    <span
                      aria-hidden
                      className={`absolute top-2 left-2 size-6 grid place-items-center rounded-full border ${
                        isSel ? "bg-ink text-cream border-ink" : "bg-background/80 border-ink/40 text-transparent"
                      }`}
                    >
                      <Check className="size-3.5" strokeWidth={2.5} />
                    </span>
                  )}
                </div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-ink/80">{item.name}</p>
                <p className="text-[10px] text-ink/55 mt-1 tracking-wide">
                  {[item.brand, item.memory?.occasion, item.memory?.person].filter(Boolean).join(" · ")}
                </p>
                {item.memory?.story ? (
                  <p className="font-serif italic text-[15px] leading-relaxed text-ink/75 mt-4 max-w-prose">
                    “{item.memory.story}”
                  </p>
                ) : (
                  <p className="text-[11px] italic text-ink/40 mt-4">
                    No story yet — tap the piece to add one.
                  </p>
                )}
              </article>
              );
            })}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-x-5 gap-y-12">
            {visible.map((item, i) => {
              const folderCount = folders.filter((f) => f.itemIds.includes(item.id)).length;
              const isSel = selected.has(item.id);
              const loan = getLoanForItem(item.id);
              return (
                <article
                  key={item.id}
                  className={`animate-rise ${selectMode ? "cursor-pointer select-none" : ""}`}
                  style={{ animationDelay: `${i * 40}ms` }}
                  onPointerDown={() => onCardPointerDown(item.id)}
                  onPointerUp={cancelLongPress}
                  onPointerLeave={cancelLongPress}
                  onPointerCancel={cancelLongPress}
                  onClick={(e) => onCardClick(item.id, e)}
                >
                  <div className={`relative w-full aspect-[3/4] bg-card mb-4 overflow-hidden shadow-[0_14px_30px_-18px_rgba(107,58,74,0.28)] transition ${
                    selectMode && isSel ? "ring-2 ring-ink ring-offset-2 ring-offset-background" : ""
                  }`}>
                    <img
                      src={item.image}
                      alt={item.name}
                      loading="lazy"
                      width={768}
                      height={1024}
                      className="w-full h-full object-cover"
                    />
                    <span className="absolute top-1 left-1 bg-black/30 backdrop-blur-sm text-white text-[7px] uppercase tracking-[0.18em] font-light px-[5px] py-[1px] rounded-full">
                      {item.season}
                    </span>
                    {loan && (
                      <Link
                        to="/lent"
                        onClick={(e) => e.stopPropagation()}
                        onPointerDown={(e) => e.stopPropagation()}
                        className="absolute bottom-1.5 left-1.5 right-1.5 inline-flex items-center justify-center bg-[#C4845A] text-white text-[8px] uppercase tracking-[0.20em] font-light px-2 py-[3px] rounded-full hover:bg-[#B0744D] transition"
                        aria-label={`Lent until ${formatDueDate(loan.due)}`}
                      >
                        Lent until {formatDueDate(loan.due)}
                      </Link>
                    )}


                    {selectMode && (
                      <span
                        aria-hidden
                        className={`absolute top-2 left-2 size-6 grid place-items-center rounded-full border ${
                          isSel ? "bg-ink text-cream border-ink" : "bg-background/80 border-ink/40 text-transparent"
                        }`}
                      >
                        <Check className="size-3.5" strokeWidth={2.5} />
                      </span>
                    )}

                    {!selectMode && !isDeparting && (
                      <button
                        type="button"
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={(e) => { e.stopPropagation(); setTagging(item); }}
                        aria-label={`Add ${item.name} to a folder`}
                        className={`absolute top-2 right-2 size-8 grid place-items-center transition active:scale-90 ${
                          folderCount > 0 ? "text-foreground" : "text-foreground/50"
                        }`}
                      >
                        <Bookmark className="size-[15px]" strokeWidth={1.25} fill={folderCount > 0 ? "currentColor" : "none"} />
                      </button>
                    )}

                  </div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-foreground leading-tight">{item.name}</p>
                  <p className="text-[10px] text-muted-foreground mt-1 tracking-wide">
                    {[item.brand, item.color].filter(Boolean).join(" · ")}
                    {folderCount > 0 && !isDeparting && <span className="ml-1 italic"> · in {folderCount}</span>}
                  </p>
                  {isDeparting && item.departing && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className={`inline-flex items-center gap-1 text-[9px] uppercase tracking-[0.18em] px-2 py-0.5 border ${
                        item.departing.intent === "sell"
                          ? "border-mauve/40 text-mauve bg-mauve/5"
                          : item.departing.intent === "giveaway"
                            ? "border-ink/30 text-ink/70 bg-ink/5"
                            : "border-mint/50 text-mint bg-mint/5"
                      }`}>
                        <Tag className="size-2.5" strokeWidth={1.5} />
                        {item.departing.intent === "sell" ? "To sell" : item.departing.intent === "giveaway" ? "Giveaway" : "Donate"}
                      </span>
                      {item.departing.listed && (
                        <span className="text-[9px] uppercase tracking-[0.18em] text-mint italic">Listed</span>
                      )}
                    </div>
                  )}
                  {isDeparting && item.departing?.notes && (
                    <p className="font-serif italic text-[12px] text-ink/55 mt-2 leading-snug">{item.departing.notes}</p>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
      </div>

      {/* Multi-select bottom action bar */}
      {selectMode && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-ink/15 bg-cream/95 backdrop-blur-md px-5 pt-3 pb-[max(env(safe-area-inset-bottom),1rem)] shadow-[0_-12px_30px_-18px_rgba(0,0,0,0.25)]">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={exitSelectMode}
                aria-label="Exit selection"
                className="size-8 grid place-items-center text-ink/70 hover:text-ink"
              >
                <X className="size-4" strokeWidth={1.5} />
              </button>
              <p className="text-[11px] uppercase tracking-[0.22em] text-ink">
                {selected.size} selected
              </p>
            </div>
            <button
              type="button"
              onClick={toggleSelectAll}
              className="text-[10px] uppercase tracking-[0.22em] text-mauve hover:text-ink transition"
            >
              {allSelected ? "Clear all" : "Select all"}
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {tab !== "active" && (
              <ActionBarButton icon={Sparkles} label="Active" onClick={() => bulkMove("active")} disabled={selected.size === 0} />
            )}
            {tab !== "archived" && (
              <ActionBarButton icon={Archive} label="Archived" onClick={() => bulkMove("archived")} disabled={selected.size === 0} />
            )}
            {tab !== "departing" && (
              <ActionBarButton icon={Tag} label="Departing" onClick={() => bulkMove("departing")} disabled={selected.size === 0} />
            )}
            {tab !== "vault" && (
              <ActionBarButton icon={Heart} label="Memory Vault" onClick={() => bulkMove("vault")} disabled={selected.size === 0} />
            )}
          </div>
        </div>
      )}





      {/* Tag-to-folder sheet */}
      <Sheet open={!!tagging} onOpenChange={(o) => !o && setTagging(null)}>
        <SheetContent side="bottom" className="rounded-t-3xl border-border max-h-[80vh] overflow-y-auto">
          <SheetHeader className="text-left">
            <p className="text-[10px] uppercase tracking-[0.22em] text-mint">Save to collection</p>
            <SheetTitle className="font-serif text-2xl leading-tight tracking-[0.02em]">
              {tagging?.name}
            </SheetTitle>
            <SheetDescription className="text-xs">
              Tap any folder to add or remove this piece.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-5 space-y-2">
            {folders.length === 0 && (
              <p className="text-xs text-muted-foreground italic">No folders yet — create one below.</p>
            )}
            {folders.map((f) => {
              const inIt = tagging ? f.itemIds.includes(tagging.id) : false;
              const days = tripDays(f.startDate, f.endDate);
              return (
                <div
                  key={f.id}
                  className={`rounded-2xl border transition ${
                    inIt ? "border-foreground bg-mint-soft/40" : "border-border bg-card"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => tagging && closet.toggleItemInFolder(f.id, tagging.id)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
                  >
                    <div className="size-10 rounded-lg overflow-hidden bg-mint-soft shrink-0">
                      {f.cover ? (
                        <img src={f.cover} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full grid place-items-center font-serif text-mint text-lg tracking-[0.02em]">
                          {f.name.charAt(0)}
                        </div>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{f.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {f.itemIds.length} items
                        {days.length > 0 && ` · ${days.length}-day trip`}
                      </p>
                    </div>
                    <span
                      className={`size-6 rounded-full grid place-items-center ${
                        inIt ? "bg-foreground text-background" : "border border-border text-transparent"
                      }`}
                    >
                      <Check className="size-3.5" strokeWidth={2.25} />
                    </span>
                  </button>

                  {days.length > 0 && tagging && (
                    <div className="px-3 pb-3 pt-1">
                      <p className="text-[9px] uppercase tracking-[0.18em] text-muted-foreground mb-1.5">
                        Wear on
                      </p>
                      <div className="flex gap-1.5 overflow-x-auto no-scrollbar">
                        {days.map((d) => {
                          const date = new Date(d + "T00:00:00");
                          const label = date.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
                          const assigned = f.dayAssignments?.[d]?.includes(tagging.id) ?? false;
                          return (
                            <button
                              key={d}
                              type="button"
                              onClick={() => closet.toggleItemOnDay(f.id, d, tagging.id)}
                              className={`shrink-0 px-2.5 py-1 rounded-full text-[10px] tracking-wide border transition ${
                                assigned
                                  ? "bg-foreground text-background border-foreground"
                                  : "bg-background text-muted-foreground border-border"
                              }`}
                            >
                              {label}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              const name = newFolder.trim();
              if (!name || !tagging) return;
              const f = closet.createFolder(name);
              closet.toggleItemInFolder(f.id, tagging.id);
              setNewFolder("");
            }}
            className="mt-5 pt-4 border-t border-border flex gap-2"
          >
            <div className="relative flex-1">
              <FolderPlus className="size-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={newFolder}
                onChange={(e) => setNewFolder(e.target.value)}
                placeholder="New folder name"
                className="w-full rounded-full bg-card border border-border pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-mint/30"
              />
            </div>
            <button
              type="submit"
              disabled={!newFolder.trim()}
              className="rounded-full bg-foreground text-background px-4 text-xs font-medium active:scale-95 transition disabled:opacity-40"
            >
              Create + add
            </button>
          </form>

          <Link
            to="/folders"
            onClick={() => setTagging(null)}
            className="block text-center mt-4 text-[11px] text-mint italic underline underline-offset-4"
          >
            Manage all folders
          </Link>
        </SheetContent>
      </Sheet>
      <LogWearSheet open={logOpen} onClose={() => setLogOpen(false)} />

      {/* Memory Vault prompt */}
      <Sheet open={!!vaultPrompt} onOpenChange={(o) => !o && setVaultPrompt(null)}>
        <SheetContent side="bottom" className="rounded-t-3xl border-border max-h-[85vh] overflow-y-auto" style={{ backgroundColor: "#EDE5DC" }}>
          <SheetHeader className="text-left">
            <p className="text-[10px] uppercase tracking-[0.22em] text-mauve inline-flex items-center gap-1.5">
              <Heart className="size-3" strokeWidth={1.5} /> Memory Vault
            </p>
            <SheetTitle className="font-serif italic text-2xl leading-tight tracking-[0.01em]">
              {vaultPrompt?.name}
            </SheetTitle>
            <SheetDescription className="text-xs italic">
              Kept for what it meant. This piece won't appear in outfit suggestions.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-5 space-y-4">
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-ink/60 block mb-1.5">Story</label>
              <textarea
                value={vaultStory}
                onChange={(e) => setVaultStory(e.target.value)}
                placeholder="Why are you keeping this?"
                rows={4}
                className="w-full bg-cream/60 border border-ink/15 px-3 py-2.5 text-sm font-serif italic leading-relaxed focus:outline-none focus:border-ink/40"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] uppercase tracking-[0.22em] text-ink/60 block mb-1.5">Occasion or date</label>
                <input
                  value={vaultOccasion}
                  onChange={(e) => setVaultOccasion(e.target.value)}
                  placeholder="e.g. Wedding, Summer '19"
                  className="w-full bg-cream/60 border border-ink/15 px-3 py-2 text-sm focus:outline-none focus:border-ink/40"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-[0.22em] text-ink/60 block mb-1.5">Person (optional)</label>
                <input
                  value={vaultPerson}
                  onChange={(e) => setVaultPerson(e.target.value)}
                  placeholder="e.g. Mum"
                  className="w-full bg-cream/60 border border-ink/15 px-3 py-2 text-sm focus:outline-none focus:border-ink/40"
                />
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={saveVaultMemory}
            className="mt-6 w-full bg-ink text-cream text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-ink/90 transition"
          >
            Keep in Memory Vault
          </button>
        </SheetContent>
      </Sheet>

      {/* Departing prompt */}
      <Sheet open={!!departingPrompt} onOpenChange={(o) => !o && setDepartingPrompt(null)}>
        <SheetContent side="bottom" className="rounded-t-3xl border-border max-h-[85vh] overflow-y-auto">
          <SheetHeader className="text-left">
            <p className="text-[10px] uppercase tracking-[0.22em] text-mauve inline-flex items-center gap-1.5">
              <Tag className="size-3" strokeWidth={1.5} /> Departing
            </p>
            <SheetTitle className="font-serif text-2xl leading-tight tracking-[0.01em]">
              {departingPrompt?.name}
            </SheetTitle>
            <SheetDescription className="text-xs">
              On its way out. It won't appear in outfit suggestions.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-5 space-y-4">
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-ink/60 mb-2">Intent</p>
              <div className="grid grid-cols-3 gap-2">
                {(["sell", "giveaway", "donate"] as const).map((intent) => {
                  const on = departIntent === intent;
                  return (
                    <button
                      key={intent}
                      type="button"
                      onClick={() => setDepartIntent(intent)}
                      className={`text-[10px] uppercase tracking-[0.18em] py-2.5 border transition ${
                        on ? "border-sage bg-sage text-cream" : "border-ink/25 text-ink/70 hover:border-ink/50"
                      }`}
                    >
                      {intent === "sell" ? "Sell" : intent === "giveaway" ? "Giveaway" : "Donate"}
                    </button>
                  );
                })}
              </div>
            </div>

            {departIntent === "sell" && (
              <label className="flex items-center gap-2 text-xs text-ink/75">
                <input
                  type="checkbox"
                  checked={departListed}
                  onChange={(e) => setDepartListed(e.target.checked)}
                  className="size-4 accent-ink"
                />
                Already listed (Vinted, Depop, eBay…)
              </label>
            )}

            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-ink/60 block mb-1.5">Notes (optional)</label>
              <textarea
                value={departNotes}
                onChange={(e) => setDepartNotes(e.target.value)}
                placeholder={departIntent === "sell" ? "Price, condition, where it's listed…" : departIntent === "giveaway" ? "Who is it for? Pickup date?" : "Which charity? When are you dropping it off?"}
                rows={3}
                className="w-full bg-cream/60 border border-ink/15 px-3 py-2.5 text-sm leading-relaxed focus:outline-none focus:border-ink/40"
              />
            </div>
          </div>

          <button
            type="button"
            onClick={saveDeparting}
            className="mt-6 w-full bg-ink text-cream text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-ink/90 transition"
          >
            Move to Departing
          </button>
        </SheetContent>
      </Sheet>

      {/* Tap-to-detail bottom sheet */}
      <Sheet open={!!detailItem} onOpenChange={(o) => !o && setDetailItem(null)}>
        <SheetContent side="bottom" className="bg-cream border-t border-ink/15 max-h-[88vh] overflow-y-auto">
          {detailItem && (() => {
            const it = detailItem;
            const status: ItemStatus = it.status ?? "active";
            const close = () => setDetailItem(null);
            const move = (to: ItemStatus) => {
              close();
              // small delay so the close animation doesn't fight the next sheet
              setTimeout(() => handleMove(it, to), 80);
            };
            const editMemory = () => {
              close();
              setTimeout(() => {
                setVaultStory(it.memory?.story ?? "");
                setVaultOccasion(it.memory?.occasion ?? "");
                setVaultPerson(it.memory?.person ?? "");
                setVaultPrompt(it);
              }, 80);
            };
            const editDeparting = () => {
              close();
              setTimeout(() => {
                setDepartIntent(it.departing?.intent ?? "sell");
                setDepartNotes(it.departing?.notes ?? "");
                setDepartListed(it.departing?.listed ?? false);
                setDepartingPrompt(it);
              }, 80);
            };
            const addToFolder = () => {
              close();
              setTimeout(() => setTagging(it), 80);
            };
            return (
              <>
                <SheetHeader className="text-left">
                  <SheetTitle className="font-serif text-2xl tracking-[0.04em] uppercase">{it.name}</SheetTitle>
                  <SheetDescription className="text-[10px] uppercase tracking-[0.22em] text-mauve">
                    {STATUS_LABELS[status]} · {[it.brand, it.color, it.season].filter(Boolean).join(" · ")}
                  </SheetDescription>
                </SheetHeader>

                <div className="mt-5 w-full aspect-[4/5] bg-card overflow-hidden">
                  <img src={it.image} alt={it.name} className="w-full h-full object-cover" />
                </div>

                {it.memory?.story && (
                  <p className="font-serif italic text-[14px] leading-relaxed text-ink/75 mt-4">
                    “{it.memory.story}”
                  </p>
                )}
                {it.departing?.notes && (
                  <p className="font-serif italic text-[13px] text-ink/65 mt-4">{it.departing.notes}</p>
                )}

                <div className="mt-6 grid grid-cols-2 gap-2">
                  <ActionBarButton icon={Pencil} label="Edit item" onClick={() => { close(); void navigate({ to: "/item/$itemId", params: { itemId: it.id } }); }} />
                  {status !== "departing" && status !== "active" && <ActionBarButton icon={Heart} label="Edit memory" onClick={editMemory} />}
                  {status !== "vault" && status !== "active" && <ActionBarButton icon={Tag} label="Edit departing" onClick={editDeparting} />}
                  <ActionBarButton icon={FolderPlus} label="Add to folder" onClick={addToFolder} />
                  {status !== "active" && (
                    <ActionBarButton icon={Sparkles} label="Move to Active" onClick={() => move("active")} />
                  )}
                  {status !== "archived" && (
                    <ActionBarButton icon={Archive} label="Move to Archived" onClick={() => move("archived")} />
                  )}
                  {status !== "departing" && (
                    <ActionBarButton icon={Tag} label="Move to Departing" onClick={() => move("departing")} />
                  )}
                  {status !== "vault" && (
                    <ActionBarButton icon={Heart} label="Move to Vault" onClick={() => move("vault")} />
                  )}
                </div>
              </>
            );
          })()}
        </SheetContent>
      </Sheet>
    </PageShell>
  );
}



function ActionBarButton({
  icon: Icon,
  label,
  onClick,
  disabled,
}: {
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center justify-center gap-2 border border-ink/25 px-3 py-2.5 text-[10px] uppercase tracking-[0.18em] text-ink hover:bg-ink hover:text-cream transition disabled:opacity-40 disabled:cursor-not-allowed"
    >
      <Icon className="size-3.5" strokeWidth={1.5} />
      {label}
    </button>
  );
}
