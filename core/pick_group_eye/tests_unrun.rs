// AUTHORED ONLY / UNRUN. No numerical/image acceptance is claimed.
use super::*;
#[test]
fn strict_boundary_and_default_off_unrun() {
    assert_eq!(lrt_pick_group_eye_evaluate_v1(0, 0, 0, 0), 0);
    assert_eq!(lrt_pick_group_eye_evaluate_v1(3, 1, 2, 32), 2);
    assert_eq!(lrt_pick_group_eye_evaluate_v1(3, 1, 3, 32), 2);
    assert_eq!(lrt_pick_group_eye_evaluate_v1(3, 1, 4, 32), 3);
    assert_eq!(lrt_pick_group_eye_evaluate_v1(31, 1, 32, 32), 3);
}
#[test]
fn missing_failed_stale_and_invalid_never_omit_unrun() {
    for n in [0, 4, 32] { assert_eq!(lrt_pick_group_eye_evaluate_v1(3, 0, n, 32), 1); }
    for (n, limit) in [(0, 32), (33, 32), (4, 8)] {
        assert_eq!(lrt_pick_group_eye_evaluate_v1(3, 1, n, limit), 1);
    }
    assert_eq!(lrt_pick_group_eye_evaluate_v1(32, 1, 32, 32), -1);
    assert_eq!(lrt_pick_group_eye_evaluate_v1(3, 2, 4, 32), -1);
}
