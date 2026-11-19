"""Short explanations behind the "?" buttons: (title, text, example). {one}/{many}/{period} are
replaced with the project's own words."""

HELP = {
    "terms": ("Wording",
              "Choose the words used everywhere in the app and in the exported files: what you randomize, "
              "and what one period of the schedule is called.",
              "Participants · Sessions gives \"18 participants received all 3 treatments, one per session.\""),
    "subjects": ("The {one} table",
                 "One row per {one}, in the order they enter the study (enrollment order). The first column "
                 "you choose holds the IDs; other columns describe groups such as sex, genotype or cage. "
                 "Paste straight from Excel with Ctrl+V.",
                 "ID | Sex | Cage\nM01 | male | C1\nF01 | female | C2"),
    "strata": ("Balance within groups",
               "Each group you tick gets its own balanced design, so the treatments are spread evenly "
               "within males and within females, not only overall.",
               "Tick Sex: in every {period}, males get each treatment equally often, and so do females."),
    "cluster": ("Same treatment for a whole cage",
                "Use this when {many} cannot be treated separately, for example when a drug is in the "
                "drinking water. The cage (or litter, tank...) becomes the unit: cages are randomized and "
                "every {one} in a cage gets the cage's sequence. Balance is counted in cages.",
                "12 cages × 4 rats, 3 treatments: each treatment goes to 4 cages in every {period}."),
    "design": ("Design type",
               "Crossover: every {one} gets every treatment, once each, in its own order. "
               "Incomplete: every {one} gets only some of the treatments. Replicated: treatments are given "
               "more than once. Parallel groups: every {one} gets one treatment.",
               "4 doses, 24 rats, each rat gets all 4 doses over 4 weeks: crossover."),
    "treatments": ("Treatments",
                   "The conditions to randomize, one per row. The ratio column (parallel and incomplete "
                   "designs only) sets how often each is used relative to the others.",
                   "Vehicle 1, Drug 2: twice as many {many} get the drug."),
    "fixed": ("Fixed {periods}",
              "{Periods} that are the same for everyone and not randomized, such as a baseline before "
              "or a maximal dose after the randomized part. Numbers count on the full timeline.",
              "5 randomized weeks and MAX in week 6: add a fixed period 6 called MAX."),
    "period_name": ("Name of a period",
                    "What one step of the schedule is called. Used in tables, pictures and the methods text.",
                    "Week, Day, Session, Visit"),
    "forbidden_transitions": ("Never directly followed by",
                              "A pair of treatments that must never be given in consecutive {periods}, "
                              "for safety or to avoid interactions.",
                              "High dose → Drug B: no {one} gets Drug B the {period} after the high dose."),
    "forbidden_periods": ("Not allowed in a {period}",
                          "A treatment that must never be given in a particular {period}.",
                          "Drug not in {period_cap} 1: everyone starts with something else."),
    "order_rules": ("Must come before",
                    "Treatment A must always be given before treatment B (not necessarily directly). "
                    "Use it for dose escalation.",
                    "Low before High: no {one} gets High before Low."),
    "period_balance": ("Each {period} has each treatment equally often",
                       "Time effects (habituation, age, season) then hit every treatment equally. "
                       "When the numbers do not divide evenly, counts differ by at most 1.",
                       "24 rats, 4 doses: every week, 6 rats get each dose."),
    "carryover_balance": ("Carry-over balance",
                          "Each treatment is directly preceded by every other treatment equally often, so "
                          "any after-effect of the previous treatment is spread evenly.",
                          "Low follows Vehicle as often as it follows High."),
    "cooccurrence_balance": ("Pairs balanced",
                             "Incomplete designs only: every pair of treatments is given to the same {one} "
                             "equally often, so all comparisons are equally precise.",
                             "A and B are given together as often as A and C."),
    "spread_balance": ("Spread",
                       "Within each change from one {period} to the next, {many} who shared a treatment "
                       "move on to different treatments. This makes the next treatment hard to predict.",
                       "Of the 3 rats on Low this week, each gets a different dose next week."),
    "fulllist_balance": ("Full list",
                         "Someone who sees the whole schedule list and knows which group a {one} is in can "
                         "often tell all of the {one}'s later treatments after the first two {periods}. "
                         "This criterion makes that harder. It makes the next treatment after the first "
                         "{period} somewhat easier to guess, and spread less even, so use it only if people "
                         "who test or score {many} might see the list.",
                         "Off for most studies; Preferred when the person who tests also prepares from the list."),
    "levels": ("Required, Preferred, Off",
               "Required: must hold exactly, or no schedule is produced. Preferred: met exactly when "
               "possible, otherwise as closely as possible. The criteria are improved one at a time in the "
               "order shown, so a lower one never makes a higher one worse. Off: ignored.",
               "Most studies: {period} balance Required, the rest Preferred."),
    "scope": ("Within each group too",
              "Apply carry-over, pair and spread balance within every group as well as overall. "
              "{period_cap} balance always holds within groups.",
              "Males and females are each carry-over balanced."),
    "blocks": ("Enrollment blocks",
               "Balance also holds within consecutive blocks of {many} in table order. If recruitment "
               "stops early, the {many} enrolled so far are still balanced. Several sizes are picked at "
               "random, so the next allocation is harder to guess.",
               "Sizes 4, 6: blocks of 4 or 6 consecutive {many}."),
    "seed": ("Seed",
             "The number that drives every random choice. Recorded in every export, so the schedule can "
             "be re-created and checked later.",
             "Seed 48213 with the same settings gives the same schedule again."),
    "time_limit": ("Time limit",
                   "How long the solver may search. Small designs finish in seconds. Larger ones use "
                   "the time to improve balance; more time can give a better schedule. With Reproducible "
                   "on, this is a fixed amount of search (about this many seconds on a typical laptop), "
                   "so a slower computer takes longer but finds the same schedule.",
                   "60 seconds suits up to six treatments; with seven or more, allow several minutes (e.g. 300 s)."),
    "deterministic": ("Reproducible",
                      "On: the search is measured in solver work instead of seconds, so the same seed and "
                      "settings give exactly the same schedule on any computer with the same LIBRA version. "
                      "Off: the search stops after the time limit, which can give a different (equally "
                      "valid) schedule on a faster or busier computer.",
                      "Keep it on for real studies, so that anyone can regenerate and check the schedule."),
    "mode": ("Variety or Speed",
             "Many schedules are often equally well balanced. Variety lists them when there are not too "
             "many and draws one so that every way of giving the orders to {many} is equally likely. Speed picks one quickly; "
             "just as balanced, but some schedules come up more often than others.",
             "Use Variety for the real study, Speed while trying out settings."),
    "solver": ("Solver",
               "HiGHS is built in and free. Gurobi (a commercial solver, free for academics) can be faster "
               "on very large designs; it is offered only when it is installed and licensed on this "
               "computer. The same seed can give different schedules with different solvers.",
               ""),
    "blind": ("Blinding codes",
              "Treatments get neutral codes (A, B, C...). Exports then include a file with codes only for "
              "the experimenters and a separate code key file to keep away from them.",
              "Vehicle → C, Low → A, High → B."),
    "final": ("Final schedule",
              "Mark the schedule you will use. It is then locked: it cannot be deleted, and changes to "
              "the settings only affect new runs. The fingerprint identifies it, for example in a "
              "preregistration.",
              "Final: R3 · fingerprint 3F9A-0C21-77BE"),
    "fingerprint": ("Fingerprint",
                    "A short checksum computed from the whole schedule. Any change to any cell gives a "
                    "different fingerprint, so you can show that the schedule used is the one generated.",
                    "Quote it in a preregistration: \"schedule fingerprint 3F9A-0C21-77BE\"."),
    "verify": ("Verify",
               "Runs the solver again with the saved settings and seed and checks that it produces the "
               "same schedule. With Reproducible on, it does on any computer with the same LIBRA version. "
               "With it off, schedules that hit the time limit can differ between computers. The saved "
               "schedule stays the record either way.",
               "Before marking a schedule as final, or when a colleague checks it on their own computer."),
    "note": ("Note for this run",
             "A short label stored with the run, shown in the list of runs and in the project history.",
             "'pilot', or 'final for ethics submission'."),
    "calendar": ("Calendar",
                 "Turns {periods} into dates. A date that falls on a weekend or a listed holiday moves to "
                 "the next working day. A column with each {one}'s own start date allows staggered starts.",
                 "Start 2026-11-02, 7 days apart: {period_cap} 1 on 2 Nov, {period_cap} 2 on 9 Nov..."),
    "extend": ("Add {many}",
               "Adds new {many} to a schedule without changing anyone already scheduled. The new "
               "{many} are placed so that the whole study stays as balanced as possible.",
               "A second cohort of 8 {many} joins a study of 24."),
    "replace": ("Replace a dropout",
                "A new {one} takes over the full sequence of one who dropped out, so the balance of the "
                "design is unchanged. Both rows stay in the schedule with a status note.",
                "P07 drops out after session 1; P19 gets P07's sequence."),
}
