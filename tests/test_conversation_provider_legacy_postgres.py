"""Run existing Eval/provider regressions inside an owned UUID database.

The original modules expect an externally isolated DB. Re-export their tests
with the Conversation fixture so this increment never uses the application DB.
"""

from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_eval_recovery import cleanup_cases as cleanup_cases
from test_eval_recovery import (
    test_cancel_and_completion_commit_order as test_cancel_and_completion_commit_order,
)
from test_eval_recovery import (
    test_completed_transport_replay_is_not_new_dispatch as test_completed_transport_replay_is_not_new_dispatch,
)
from test_eval_recovery import (
    test_concurrent_cancel_completion_race_has_one_terminal_winner as test_concurrent_cancel_completion_race_has_one_terminal_winner,
)
from test_eval_recovery import test_deadline_precedes_dispatch as test_deadline_precedes_dispatch
from test_eval_recovery import (
    test_duplicate_ack_loss_and_terminal_old_delivery as test_duplicate_ack_loss_and_terminal_old_delivery,
)
from test_eval_recovery import (
    test_last_allowed_successful_dispatch_can_still_execute as test_last_allowed_successful_dispatch_can_still_execute,
)
from test_eval_recovery import (
    test_rejection_two_phase_attempts_are_network_limit as test_rejection_two_phase_attempts_are_network_limit,
)
from test_eval_recovery import (
    test_three_owner_losses_before_dispatch_are_finite as test_three_owner_losses_before_dispatch_are_finite,
)
from test_eval_recovery import (
    test_unknown_never_resends_and_retains_reservation as test_unknown_never_resends_and_retains_reservation,
)
from test_provider_phase_fencing import (
    test_actual_http_send_is_single_despite_legacy_retry_setting as test_actual_http_send_is_single_despite_legacy_retry_setting,
)
