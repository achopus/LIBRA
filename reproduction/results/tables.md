## T1 Existence and certificates

| case | expected | status | seconds |
| --- | --- | --- | --- |
| row-complete Latin square, t=2 | exists | Optimal | 0.00 |
| row-complete Latin square, t=3 | does not exist | Infeasible | 0.00 |
| row-complete Latin square, t=4 | exists | Optimal | 0.00 |
| row-complete Latin square, t=5 | does not exist | Infeasible | 0.09 |
| row-complete Latin square, t=6 | exists | Optimal | 0.08 |
| row-complete Latin square, t=7 | does not exist | Infeasible | 71.54 |
| row-complete Latin square, t=8 | exists | Time limit reached | 900.06 |
| t=3, lambda=1 | does not exist | Infeasible | 0.00 |
| t=3, lambda=2 | exists | Optimal | 0.00 |
| t=3, lambda=3 | does not exist | Infeasible | 0.01 |
| t=3, lambda=4 | exists | Optimal | 0.00 |
| t=3, lambda=5 | does not exist | Infeasible | 0.00 |
| t=3, lambda=6 | exists | Optimal | 0.00 |
| t=5, N=15 carry-over balance (Prescott 1999) | exists | Optimal | 1.95 |
| t=5, N=15 carry-over balance + perfect spread | (new) does not exist | Infeasible | 10.94 |
| t=5, N=15 carry-over balance, minimum spread excess | (new) minimum = 1 | Optimal | 49.88 |

HiGHS (highspy) 1.15.1; Williams squares t=2..12 balanced: True; diagnostics cross-check: {'random_designs_checked': 500, 'mismatches': 0}

## T2 Carry-over count range, worst unit (mean over randomizations; 0 = perfect, 1 = as even as possible)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 5.59 | 8.30 | 5.63 | 6.64 | 3.89 |
| Random Latin squares | 5.50 | 8.45 | 5.36 | 6.62 | 2.98 |
| Williams squares | 2.00 | 3.80 | 0.00 | 1.96 | 2.00 |
| Williams squares, best of 500 | 2.00 | 2.00 | 0.00 | 1.07 | 2.00 |
| Rerandomization (best 1%) | 4.07 | 6.00 | 3.52 | 5.18 | 2.00 |
| ILP without spread | 0.00 | 0.00 | 0.00 | 1.00 | 2.00 |
| ILP (full) | 0.00 | 0.00 | 0.00 | 1.00 | 2.00 |

## T3 Period imbalance (mean deviation count, all subjects)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 30.20 | 43.26 | 21.48 | 31.55 | 9.82 |
| Random Latin squares | 0.00 | 0.00 | 0.00 | 4.01 | 0.00 |
| Williams squares | 0.00 | 0.00 | 0.00 | 3.93 | 0.00 |
| Williams squares, best of 500 | 0.00 | 0.00 | 0.00 | 0.17 | 0.00 |
| Rerandomization (best 1%) | 19.11 | 29.74 | 12.12 | 20.21 | 3.58 |
| ILP without spread | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ILP (full) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## T4 Spread deviation (all subjects; lower = subjects sharing a treatment diverge more)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 17.00 | 38.94 | 15.75 | 26.59 | 5.30 |
| Random Latin squares | 14.07 | 31.77 | 11.78 | 22.00 | 2.94 |
| Williams squares | 10.12 | 23.60 | 11.56 | 21.52 | 0.00 |
| Williams squares, best of 500 | 0.00 | 0.36 | 2.00 | 22.86 | 0.00 |
| Rerandomization (best 1%) | 11.91 | 27.64 | 8.24 | 21.07 | 0.00 |
| ILP without spread | 7.88 | 18.22 | 9.17 | 16.80 | 0.00 |
| ILP (full) | 1.00 | 6.15 | 2.00 | 12.25 | 0.00 |

## T5 Mutual information between consecutive periods, per change (bits)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.921 | 0.660 | 0.717 | 1.023 | 0.714 |
| Random Latin squares | 1.224 | 0.769 | 0.877 | 1.245 | 0.892 |
| Williams squares | 1.074 | 0.674 | 0.871 | 1.236 | 0.667 |
| Williams squares, best of 500 | 0.737 | 0.408 | 0.583 | 1.301 | 0.667 |
| Rerandomization (best 1%) | 0.946 | 0.619 | 0.667 | 1.050 | 0.602 |
| ILP without spread | 1.001 | 0.615 | 0.807 | 1.159 | 0.667 |
| ILP (full) | 0.770 | 0.483 | 0.583 | 1.067 | 0.667 |

## T6 Guess accuracy, observer knows pooled transition table, after 1 observed period(s)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.405 | 0.360 | 0.481 | 0.338 | 0.677 |
| Random Latin squares | 0.416 | 0.374 | 0.534 | 0.359 | 0.748 |
| Williams squares | 0.333 | 0.322 | 0.333 | 0.236 | 0.667 |
| Williams squares, best of 500 | 0.333 | 0.250 | 0.333 | 0.233 | 0.667 |
| Rerandomization (best 1%) | 0.352 | 0.335 | 0.424 | 0.296 | 0.566 |
| ILP without spread | 0.250 | 0.250 | 0.333 | 0.235 | 0.667 |
| ILP (full) | 0.250 | 0.250 | 0.333 | 0.238 | 0.667 |

Chance: A 0.250, B 0.250, C 0.333, D 0.200, E 0.500

## T6 Guess accuracy, observer knows pooled transition table, after 2 observed period(s)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.497 | 0.448 | 0.638 | 0.395 | 1.000 |
| Random Latin squares | 0.542 | 0.469 | 0.661 | 0.403 | 1.000 |
| Williams squares | 0.391 | 0.382 | 0.500 | 0.300 | 1.000 |
| Williams squares, best of 500 | 0.500 | 0.333 | 0.500 | 0.297 | 1.000 |
| Rerandomization (best 1%) | 0.451 | 0.416 | 0.588 | 0.360 | 1.000 |
| ILP without spread | 0.333 | 0.333 | 0.500 | 0.312 | 1.000 |
| ILP (full) | 0.333 | 0.333 | 0.500 | 0.305 | 1.000 |

Chance: A 0.333, B 0.333, C 0.500, D 0.250, E 1.000

## T6 Guess accuracy, observer knows transition table of that change, after 1 observed period(s)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.559 | 0.471 | 0.580 | 0.504 | 0.738 |
| Random Latin squares | 0.568 | 0.472 | 0.593 | 0.505 | 0.748 |
| Williams squares | 0.502 | 0.432 | 0.588 | 0.501 | 0.667 |
| Williams squares, best of 500 | 0.333 | 0.335 | 0.500 | 0.512 | 0.667 |
| Rerandomization (best 1%) | 0.503 | 0.440 | 0.522 | 0.479 | 0.599 |
| ILP without spread | 0.456 | 0.402 | 0.565 | 0.468 | 0.667 |
| ILP (full) | 0.359 | 0.356 | 0.500 | 0.423 | 0.667 |

## T6 Guess accuracy, observer knows transition table of that change, after 2 observed period(s)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.658 | 0.568 | 0.734 | 0.581 | 1.000 |
| Random Latin squares | 0.673 | 0.576 | 0.735 | 0.581 | 1.000 |
| Williams squares | 0.549 | 0.495 | 0.746 | 0.576 | 1.000 |
| Williams squares, best of 500 | 0.444 | 0.391 | 0.625 | 0.589 | 1.000 |
| Rerandomization (best 1%) | 0.624 | 0.535 | 0.699 | 0.558 | 1.000 |
| ILP without spread | 0.566 | 0.504 | 0.723 | 0.532 | 1.000 |
| ILP (full) | 0.440 | 0.446 | 0.625 | 0.504 | 1.000 |

## T6 Guess accuracy, observer knows complete allocation list, after 1 observed period(s)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.559 | 0.471 | 0.580 | 0.504 | 0.738 |
| Random Latin squares | 0.568 | 0.472 | 0.593 | 0.505 | 0.748 |
| Williams squares | 0.502 | 0.432 | 0.588 | 0.501 | 0.667 |
| Williams squares, best of 500 | 0.333 | 0.335 | 0.500 | 0.512 | 0.667 |
| Rerandomization (best 1%) | 0.503 | 0.440 | 0.522 | 0.479 | 0.599 |
| ILP without spread | 0.456 | 0.402 | 0.565 | 0.468 | 0.667 |
| ILP (full) | 0.359 | 0.356 | 0.500 | 0.423 | 0.667 |

## T6 Guess accuracy, observer knows complete allocation list, after 2 observed period(s)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.814 | 0.721 | 0.806 | 0.813 | 1.000 |
| Random Latin squares | 0.852 | 0.732 | 0.816 | 0.838 | 1.000 |
| Williams squares | 0.901 | 0.734 | 0.822 | 0.839 | 1.000 |
| Williams squares, best of 500 | 1.000 | 0.769 | 0.688 | 0.879 | 1.000 |
| Rerandomization (best 1%) | 0.856 | 0.713 | 0.799 | 0.835 | 1.000 |
| ILP without spread | 0.913 | 0.741 | 0.802 | 0.869 | 1.000 |
| ILP (full) | 0.974 | 0.738 | 0.688 | 0.907 | 1.000 |

## T7 Efficiency (model without carry-over)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.928 | 0.964 | 0.935 | 0.950 | 0.865 |
| Random Latin squares | 1.000 | 1.000 | 1.000 | 0.992 | 1.000 |
| Williams squares | 1.000 | 1.000 | 1.000 | 0.992 | 1.000 |
| Williams squares, best of 500 | 1.000 | 1.000 | 1.000 | 0.996 | 1.000 |
| Rerandomization (best 1%) | 0.969 | 0.983 | 0.977 | 0.969 | 0.978 |
| ILP without spread | 1.000 | 1.000 | 1.000 | 0.996 | 1.000 |
| ILP (full) | 1.000 | 1.000 | 1.000 | 0.996 | 1.000 |

## T7 Efficiency (model with carry-over)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.808 | 0.875 | 0.786 | 0.865 | 0.581 |
| Random Latin squares | 0.855 | 0.897 | 0.804 | 0.894 | 0.556 |
| Williams squares | 0.917 | 0.932 | 0.909 | 0.949 | 0.733 |
| Williams squares, best of 500 | 0.917 | 0.947 | 0.909 | 0.958 | 0.733 |
| Rerandomization (best 1%) | 0.884 | 0.912 | 0.858 | 0.904 | 0.761 |
| ILP without spread | 0.947 | 0.947 | 0.909 | 0.958 | 0.733 |
| ILP (full) | 0.947 | 0.947 | 0.909 | 0.958 | 0.733 |

## T7 Efficiency (20% miss last period)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.876 | 0.913 | 0.871 | 0.908 | 0.744 |
| Random Latin squares | 0.944 | 0.947 | 0.931 | 0.949 | 0.867 |
| Williams squares | 0.944 | 0.947 | 0.931 | 0.949 | 0.867 |
| Williams squares, best of 500 | 0.944 | 0.947 | 0.930 | 0.952 | 0.868 |
| Rerandomization (best 1%) | 0.914 | 0.930 | 0.908 | 0.926 | 0.847 |
| ILP without spread | 0.944 | 0.947 | 0.931 | 0.952 | 0.868 |
| ILP (full) | 0.944 | 0.947 | 0.931 | 0.952 | 0.867 |

## T7 Efficiency (10% observations missing)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.788 | 0.836 | 0.804 | 0.825 | 0.686 |
| Random Latin squares | 0.849 | 0.867 | 0.860 | 0.862 | 0.801 |
| Williams squares | 0.849 | 0.867 | 0.861 | 0.861 | 0.800 |
| Williams squares, best of 500 | 0.849 | 0.867 | 0.860 | 0.864 | 0.800 |
| Rerandomization (best 1%) | 0.822 | 0.852 | 0.840 | 0.841 | 0.782 |
| ILP without spread | 0.849 | 0.867 | 0.860 | 0.864 | 0.800 |
| ILP (full) | 0.849 | 0.867 | 0.861 | 0.865 | 0.799 |

## T7 Efficiency (one subject per stratum leaves halfway)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.894 | 0.930 | 0.849 | 0.889 | 0.806 |
| Random Latin squares | 0.963 | 0.965 | 0.908 | 0.928 | 0.933 |
| Williams squares | 0.963 | 0.965 | 0.909 | 0.928 | 0.933 |
| Williams squares, best of 500 | 0.963 | 0.965 | 0.908 | 0.931 | 0.933 |
| Rerandomization (best 1%) | 0.933 | 0.948 | 0.887 | 0.906 | 0.914 |
| ILP without spread | 0.963 | 0.965 | 0.908 | 0.932 | 0.933 |
| ILP (full) | 0.963 | 0.965 | 0.908 | 0.931 | 0.933 |

## T8 Type I error, global F (nominal 0.05; MCSE 0.005)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.043 | 0.059 | 0.057 | 0.049 | 0.050 |
| Random Latin squares | 0.058 | 0.052 | 0.054 | 0.058 | 0.051 |
| Williams squares | 0.047 | 0.048 | 0.045 | 0.052 | 0.044 |
| Williams squares, best of 500 | 0.048 | 0.048 | 0.057 | 0.045 | 0.051 |
| Rerandomization (best 1%) | 0.057 | 0.049 | 0.052 | 0.049 | 0.051 |
| ILP without spread | 0.051 | 0.053 | 0.049 | 0.044 | 0.059 |
| ILP (full) | 0.045 | 0.054 | 0.054 | 0.047 | 0.046 |

## T8 Power, global F (dose-response, 1 SD)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.574 | 0.930 | 0.615 | 0.798 | 0.328 |
| Random Latin squares | 0.648 | 0.939 | 0.653 | 0.805 | 0.403 |
| Williams squares | 0.638 | 0.954 | 0.654 | 0.809 | 0.384 |
| Williams squares, best of 500 | 0.639 | 0.948 | 0.653 | 0.809 | 0.383 |
| Rerandomization (best 1%) | 0.627 | 0.946 | 0.649 | 0.800 | 0.367 |
| ILP without spread | 0.648 | 0.947 | 0.663 | 0.804 | 0.376 |
| ILP (full) | 0.636 | 0.942 | 0.645 | 0.816 | 0.383 |

## T8 Empirical SE of high-vs-vehicle contrast

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.382 | 0.264 | 0.371 | 0.323 | 0.508 |
| Random Latin squares | 0.358 | 0.261 | 0.350 | 0.317 | 0.478 |
| Williams squares | 0.361 | 0.255 | 0.367 | 0.320 | 0.476 |
| Williams squares, best of 500 | 0.355 | 0.256 | 0.347 | 0.308 | 0.466 |
| Rerandomization (best 1%) | 0.361 | 0.258 | 0.352 | 0.319 | 0.472 |
| ILP without spread | 0.369 | 0.254 | 0.349 | 0.322 | 0.469 |
| ILP (full) | 0.369 | 0.257 | 0.352 | 0.316 | 0.466 |

## T8 Bias with unmodelled carry-over (true theta = 1)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | -0.101 | -0.106 | -0.128 | -0.083 | -0.166 |
| Random Latin squares | -0.091 | -0.101 | -0.122 | -0.081 | -0.163 |
| Williams squares | -0.097 | -0.100 | -0.129 | -0.088 | -0.174 |
| Williams squares, best of 500 | -0.096 | -0.115 | -0.115 | -0.062 | -0.161 |
| Rerandomization (best 1%) | -0.102 | -0.096 | -0.139 | -0.073 | -0.162 |
| ILP without spread | -0.090 | -0.096 | -0.122 | -0.075 | -0.160 |
| ILP (full) | -0.101 | -0.103 | -0.123 | -0.092 | -0.148 |

## T8 Empirical SE with carry-over modelled

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.405 | 0.277 | 0.398 | 0.334 | 0.625 |
| Random Latin squares | 0.388 | 0.266 | 0.397 | 0.346 | 0.711 |
| Williams squares | 0.381 | 0.264 | 0.375 | 0.324 | 0.553 |
| Williams squares, best of 500 | 0.383 | 0.261 | 0.367 | 0.328 | 0.566 |
| Rerandomization (best 1%) | 0.388 | 0.269 | 0.366 | 0.328 | 0.533 |
| ILP without spread | 0.381 | 0.267 | 0.368 | 0.328 | 0.556 |
| ILP (full) | 0.382 | 0.267 | 0.373 | 0.330 | 0.544 |

## T8 Coverage of 95% CI

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 0.949 | 0.950 | 0.950 | 0.954 | 0.946 |
| Random Latin squares | 0.952 | 0.947 | 0.943 | 0.951 | 0.951 |
| Williams squares | 0.952 | 0.958 | 0.940 | 0.949 | 0.952 |
| Williams squares, best of 500 | 0.961 | 0.952 | 0.958 | 0.955 | 0.960 |
| Rerandomization (best 1%) | 0.958 | 0.948 | 0.954 | 0.947 | 0.951 |
| ILP without spread | 0.955 | 0.955 | 0.954 | 0.947 | 0.951 |
| ILP (full) | 0.946 | 0.952 | 0.946 | 0.951 | 0.951 |

## T9 Permutation tests (rejection rate at 0.05; 1000 datasets; MCSE ~0.007 under null)

| config | scenario | naive | orbit | pipeline |
| --- | --- | --- | --- | --- |
| A | effect | 0.625 | 0.627 | 0.625 |
| A | no_effect | 0.040 | 0.036 | 0.044 |
| B | effect | 0.928 | 0.925 | 0.926 |
| B | no_effect | 0.040 | 0.044 | 0.033 |
| D | effect | 0.776 | 0.771 | 0.781 |
| D | no_effect | 0.055 | 0.060 | 0.058 |

## T10 Exchangeability (Monte Carlo p-values; large = consistent with exact symmetry)

| method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| ilp | 0.439 | 0.552 | 0.275 | 0.418 | 0.751 |
| ilp_nospread | 0.378 | 0.972 | 0.805 | 0.060 | 0.742 |
| simple | 0.911 | 0.973 | 0.948 | 0.312 | 0.016 |
| williams | 0.721 | 0.752 | 0.271 | 0.870 | 0.315 |

Replication on fresh pools (120 designs, new seeds):

| config | method | designs | mc_p_value |
| --- | --- | --- | --- |
| B | ilp | 120 | 0.693 |
| D | ilp_nospread | 120 | 0.773 |
| A | ilp | 120 | 0.871 |

## T11 Distinct design skeletons among 60 randomizations (up to relabelling/re-ordering)

| Method | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Simple (random orders) | 60 | 60 | 60 | 60 | 54 |
| Random Latin squares | 60 | 60 | 59 | 60 | 2 |
| Williams squares | 4 | 56 | 22 | 60 | 1 |
| Rerandomization (best 1%) | 60 | 60 | 60 | 60 | 4 |
| ILP without spread | 59 | 60 | 15 | 60 | 1 |
| ILP (full) | 2 | 60 | 2 | 60 | 1 |

## T12 Uniformity among all optimal designs (exhaustive enumeration, 300 seeds)

| t | N | period_balanced_designs | optimal_designs | seeds | all_outputs_optimal | distinct_outputs | share_of_optimal_set_reached | chi2_uniformity_p | max_over_expected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 6 | 3 | 1 | 300 | True | 1 | 1.000 | nan | 1.000 |
| 3 | 9 | 4 | 2 | 300 | True | 2 | 1.000 | 0.050 | 1.113 |
| 4 | 4 | 24 | 6 | 300 | True | 6 | 1.000 | 0.555 | 1.160 |
| 4 | 8 | 411 | 12 | 300 | True | 12 | 1.000 | 0.091 | 1.440 |

## T13 Scalability (60 s limit)

| t | N | strata | seconds | proven_optimal | formulation | level_carryover | level_spread | period_dev | carry_range_worst | spread_dev_all |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 6 | 1 | 0.0 | True | sequence counts | required | required | 0 | 0 | 0 |
| 3 | 6 | 2 | 0.1 | True | sequence counts | preferred | preferred | 0 | 2 | 0 |
| 3 | 9 | 1 | 0.1 | True | sequence counts | preferred | preferred | 0 | 2 | 0 |
| 3 | 9 | 2 | 0.2 | True | sequence counts | preferred | preferred | 0 | 2 | 0 |
| 3 | 14 | 1 | 0.1 | True | sequence counts | preferred | preferred | 0 | 2 | 0 |
| 3 | 14 | 2 | 0.3 | True | sequence counts | preferred | preferred | 0 | 2 | 0 |
| 4 | 8 | 1 | 0.1 | True | sequence counts | required | preferred | 0 | 0 | 2 |
| 4 | 8 | 2 | 0.1 | True | sequence counts | required | preferred | 0 | 0 | 2 |
| 4 | 12 | 1 | 0.1 | True | sequence counts | required | required | 0 | 0 | 0 |
| 4 | 12 | 2 | 1.6 | True | sequence counts | required | preferred | 0 | 1 | 12 |
| 4 | 18 | 1 | 153.3 | True | sequence counts | required | required | 0 | 1 | 0 |
| 4 | 18 | 2 | 135.2 | False | sequence counts | required | preferred | 0 | 1 | 8 |
| 5 | 10 | 1 | 11.6 | True | sequence counts | required | required | 0 | 0 | 0 |
| 5 | 10 | 2 | 32.0 | True | sequence counts | preferred | preferred | 0 | 2 | 0 |
| 5 | 15 | 1 | 84.2 | False | sequence counts | required | preferred | 0 | 0 | 1 |
| 5 | 15 | 2 | 60.1 | False | sequence counts | required | preferred | 0 | 1 | 3 |
| 5 | 22 | 1 | 167.1 | True | sequence counts | required | required | 0 | 1 | 0 |
| 5 | 22 | 2 | 159.8 | True | sequence counts | required | preferred | 0 | 1 | 0 |
| 6 | 12 | 1 | 133.3 | True | sequence counts | required | required | 0 | 0 | 0 |
| 6 | 12 | 2 | 9.6 | True | sequence counts | required | required | 0 | 0 | 0 |
| 6 | 18 | 1 | 212.4 | True | sequence counts | required | required | 0 | 0 | 0 |
| 6 | 18 | 2 | 195.1 | False | sequence counts | required | preferred | 0 | 1 | 6 |
| 6 | 26 | 1 | 295.4 | True | sequence counts | required | required | 0 | 1 | 0 |
| 6 | 26 | 2 | 191.7 | False | sequence counts | required | preferred | 0 | 1 | 16 |
| 7 | 14 | 1 | 166.2 | True | sequence counts | required | required | 0 | 0 | 0 |
| 7 | 14 | 2 | 667.9 | False | sequence counts | preferred | preferred | 0 | 2 | 0 |
| 7 | 21 | 1 | 143.3 | True | sequence counts | required | required | 0 | 0 | 0 |
| 7 | 21 | 2 | 844.5 | False | sequence counts | preferred | preferred | 0 | 5 | 10 |
| 7 | 30 | 1 | 77.3 | True | sequence counts | required | required | 0 | 1 | 0 |
| 7 | 30 | 2 | 62.9 | True | sequence counts | required | required | 0 | 1 | 0 |
| 8 | 16 | 1 | 190.0 | True | per-subject | required | required | 0 | 0 | 0 |
| 8 | 16 | 2 | 103.5 | True | per-subject | required | required | 0 | 0 | 0 |
| 8 | 24 | 1 | 294.7 | True | per-subject | required | required | 0 | 0 | 0 |
| 8 | 24 | 2 | 2521.2 | False | per-subject | required | preferred | 0 | 1 | 8 |
| 8 | 34 | 1 | 2521.7 | False | per-subject | required | preferred | 0 | 1 | 16 |
| 8 | 34 | 2 | 2523.2 | False | per-subject | required | preferred | 0 | 1 | 20 |

## T14 Case study vs Williams (200 randomizations)

| design | carry_range[stratum 1] | carry_range[stratum 2] | carry_range[all] | spread_dev[all] | spread_dev[stratum 1] | mi_per_change | eff_M2 | G2_after1 | G3_after2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ILP (case study) | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 0.404 | 0.947 | 0.333 | 0.800 |
| Williams (mean of 200) | 2.000 | 2.000 | 3.800 | 23.600 | 10.040 | 0.674 | 0.932 | 0.432 | 0.734 |
| Williams (best of 200) | 2.000 | 2.000 | 4.000 | 0.000 | 8.000 | 0.404 | 0.933 | 0.333 | 0.733 |
