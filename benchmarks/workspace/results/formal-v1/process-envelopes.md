# Original process envelopes

Thirty original sessions; milliseconds, median [IQR], n=3 per group.
Startup includes source/seal checks, imports and fixture/owned-child preparation. Handshake is worker ready emission to parent receipt.
Worker cleanup is separately measured. Individual child startup and parent shutdown roundtrip were not instrumented; they are unavailable, never zero-filled.
Nonzero descendant exit codes are preserved in the raw ownership records, without treating every deliberate refusal as infrastructure failure.
Dependency installation and actor authoring are excluded and unmeasured. These costs are not zero.

| Track / figure | Arm | Measured interval | Median [IQR] ms |
| --- | --- | --- | --- |
| single / penguins-mass | matplotlib | process_launch_to_ready_received_ms | 8140.817 [275.149] |
| single / penguins-mass | matplotlib | process_launch_to_worker_ready_ms | 8140.440 [275.163] |
| single / penguins-mass | matplotlib | ready_emission_to_parent_receipt_ms | 0.369 [0.019] |
| single / penguins-mass | matplotlib | worker_cleanup_ms | 3.371 [0.292] |
| single / penguins-mass | graphunslopify | process_launch_to_ready_received_ms | 8695.241 [155.659] |
| single / penguins-mass | graphunslopify | process_launch_to_worker_ready_ms | 8694.834 [155.637] |
| single / penguins-mass | graphunslopify | ready_emission_to_parent_receipt_ms | 0.407 [0.022] |
| single / penguins-mass | graphunslopify | worker_cleanup_ms | 18.642 [1.459] |
| single / iris-measurements | graphunslopify | process_launch_to_ready_received_ms | 8482.911 [23.011] |
| single / iris-measurements | graphunslopify | process_launch_to_worker_ready_ms | 8480.872 [23.029] |
| single / iris-measurements | graphunslopify | ready_emission_to_parent_receipt_ms | 0.428 [0.823] |
| single / iris-measurements | graphunslopify | worker_cleanup_ms | 18.644 [4.711] |
| single / iris-measurements | matplotlib | process_launch_to_ready_received_ms | 8128.901 [143.078] |
| single / iris-measurements | matplotlib | process_launch_to_worker_ready_ms | 8128.495 [143.083] |
| single / iris-measurements | matplotlib | ready_emission_to_parent_receipt_ms | 0.377 [0.020] |
| single / iris-measurements | matplotlib | worker_cleanup_ms | 3.272 [0.049] |
| single / penguins-scatter | matplotlib | process_launch_to_ready_received_ms | 8119.206 [109.792] |
| single / penguins-scatter | matplotlib | process_launch_to_worker_ready_ms | 8118.814 [109.787] |
| single / penguins-scatter | matplotlib | ready_emission_to_parent_receipt_ms | 0.392 [0.005] |
| single / penguins-scatter | matplotlib | worker_cleanup_ms | 3.297 [0.129] |
| single / penguins-scatter | graphunslopify | process_launch_to_ready_received_ms | 8436.527 [45.413] |
| single / penguins-scatter | graphunslopify | process_launch_to_worker_ready_ms | 8436.105 [45.405] |
| single / penguins-scatter | graphunslopify | ready_emission_to_parent_receipt_ms | 0.422 [0.008] |
| single / penguins-scatter | graphunslopify | worker_cleanup_ms | 18.565 [1.508] |
| single / iris-scatter | graphunslopify | process_launch_to_ready_received_ms | 8547.607 [477.272] |
| single / iris-scatter | graphunslopify | process_launch_to_worker_ready_ms | 8547.197 [477.185] |
| single / iris-scatter | graphunslopify | ready_emission_to_parent_receipt_ms | 0.410 [0.087] |
| single / iris-scatter | graphunslopify | worker_cleanup_ms | 15.649 [0.063] |
| single / iris-scatter | matplotlib | process_launch_to_ready_received_ms | 8330.823 [499.925] |
| single / iris-scatter | matplotlib | process_launch_to_worker_ready_ms | 8330.334 [499.925] |
| single / iris-scatter | matplotlib | ready_emission_to_parent_receipt_ms | 0.425 [0.032] |
| single / iris-scatter | matplotlib | worker_cleanup_ms | 3.463 [0.033] |
| paper / whole-paper | matplotlib | process_launch_to_ready_received_ms | 8861.174 [155.191] |
| paper / whole-paper | matplotlib | process_launch_to_worker_ready_ms | 8860.851 [155.172] |
| paper / whole-paper | matplotlib | ready_emission_to_parent_receipt_ms | 0.323 [0.019] |
| paper / whole-paper | matplotlib | worker_cleanup_ms | 3.436 [0.141] |
| paper / whole-paper | matplotlib | producer_setup_including_owned_children_ms | 8246.128 [203.115] |
| paper / whole-paper | graphunslopify | process_launch_to_ready_received_ms | 8808.553 [423.857] |
| paper / whole-paper | graphunslopify | process_launch_to_worker_ready_ms | 8808.192 [423.963] |
| paper / whole-paper | graphunslopify | ready_emission_to_parent_receipt_ms | 0.361 [0.105] |
| paper / whole-paper | graphunslopify | worker_cleanup_ms | 12.959 [1.136] |
| paper / whole-paper | graphunslopify | producer_setup_including_owned_children_ms | 1087.085 [268.477] |
