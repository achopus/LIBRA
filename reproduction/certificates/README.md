# Certificates

Each file is a mixed-integer model in MPS format. Variables `n_s` count the subjects receiving each treatment order (per stratum); auxiliary variables are deviation or maximum variables. Re-solve with any MIP solver and compare with the expected result.

| File | Question | Expected | Status (HiGHS 1.15.1) | Objective | Seconds |
| --- | --- | --- | --- | --- | --- |
| t5n15_carry_spread.mps | t=5, N=15: period + carry-over balance + perfect spread | infeasible | Infeasible |  | 1.0 |
| t5n15_min_spread.mps | t=5, N=15: minimum spread excess with period and carry-over balance | optimum 10 (= one spread deviation at weight 10) | Optimal | 10.0 | 74.6 |
| t5n15_nested.mps | t=5, N=15: period + carry-over + nested (prefix) carry-over balance | infeasible | Infeasible |  | 26.7 |
| t5n15_min_g3_k2.mps | t=5, N=15: minimum full-list predictability after two observed periods | optimum 10 (G3 after two periods = 10/15) | Optimal | 10.0 | 64.6 |
| t5n2x15_min_g3_k2.mps | t=5, N=2x15: minimum full-list predictability after two observed periods | optimum 10 (G3 after two periods = 10/30) | Optimal | 10.0 | 24.5 |
| t4n2x8_min_g3_k2.mps | t=4, N=2x8: minimum full-list predictability after two observed periods | optimum 11 (G3 after two periods = 11/16) | Optimal | 11.0 | 0.2 |
| t3n9_carry.mps | t=3, N=9: period + carry-over balance (so a carry-over range of 2 is the minimum) | infeasible | Infeasible |  | 0.0 |
| t4n8_min_g3_k2.mps | t=4, N=8 (one stratum of C): minimum full-list predictability after two observed periods | optimum 7 (G3 after two periods = 7/8) | Optimal | 7.0 | 0.2 |
| t6n10_min_g3_k2.mps | t=6, N=10 (one stratum of D): minimum full-list predictability after two observed periods | optimum 6 (G3 after two periods = 6/10) | Optimal | 6.0 | 26.0 |
