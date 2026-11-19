"""A partially unblinded observer.

In the motivating study a rater may recognise some conditions (for example OTHER, or the strong
conditions OTHER and HIGH) from behaviour, but not tell the others apart. Such an observer sees only
the CLASS of each subject's past treatments and guesses the class of the next one.

Class splits (configurations A and B; indices follow the treatment order VEHICLE, LOW, HIGH,
NOMINAL, OTHER; relabelling makes any fixed choice representative):
  one      {OTHER} vs. the other four
  strong   {OTHER, HIGH} vs. {VEHICLE, LOW, NOMINAL}

Observers (accuracy of guessing the next class, averaged over subjects and observation points
k = 1 .. p-2; ties split):
  baseline   knows only that each subject gets every treatment once: guesses the majority class
             among the subject's remaining treatments (design-independent)
  table      also knows the class-level transition table of the current period change
  list       holds the full allocation list (rows, not identities) and guesses the most common
             next class among rows with the same class history

Output: results/r07_partial_observer.csv (printed)
"""
import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, load_pool

SPLITS = {"one": [4], "strong": [2, 4]}
METHODS = ["simple", "latin", "williams", "williams_best", "rerand", "classical", "sa", "ilp_nospread", "ilp"]


def accuracy(D, cls_members):
    N, p = D.shape
    cls = np.isin(D, cls_members).astype(int)                  # 1 = recognised class
    n_cls = len(cls_members)
    t = D.max() + 1
    res = {"baseline": [], "table": [], "list": []}
    for k in range(1, p - 1):                                   # history of k periods, predict k+1
        hist = [tuple(r[:k]) for r in cls]
        nxt = cls[:, k]
        # per-change class transition table: P(next class | current class)
        tab = np.zeros((2, 2))
        np.add.at(tab, (cls[:, k - 1], nxt), 1)
        for i in range(N):
            seen_strong = cls[i, :k].sum()
            remaining = np.array([t - k - (n_cls - seen_strong), n_cls - seen_strong])  # [other, recognised]
            options = [c for c in (0, 1) if remaining[c] > 0]
            # baseline
            best = [c for c in options if remaining[c] == max(remaining[o] for o in options)]
            res["baseline"].append((nxt[i] in best) / len(best))
            # table
            sc = {c: tab[cls[i, k - 1], c] for c in options}
            best = [c for c in options if sc[c] == max(sc.values())]
            res["table"].append((nxt[i] in best) / len(best))
            # list
            cnt = {c: sum(1 for j in range(N) if hist[j] == hist[i] and nxt[j] == c) for c in options}
            best = [c for c in options if cnt[c] == max(cnt.values())]
            res["list"].append((nxt[i] in best) / len(best))
    return {o: float(np.mean(v)) for o, v in res.items()}


def main():
    rows = []
    for c in ("A", "B"):
        for m in METHODS:
            try:
                pool = load_pool(c, m)[:60]
            except FileNotFoundError:
                continue
            for split, members in SPLITS.items():
                acc = pd.DataFrame([accuracy(D, members) for D in pool]).mean()
                rows.append({"config": c, "method": m, "split": split, **acc.round(4).to_dict()})
            print(c, m, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "r07_partial_observer.csv", index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
