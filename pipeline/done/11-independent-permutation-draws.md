---
id: 11
slug: independent-permutation-draws
status: done
priority: P0
title: Significance permutations must explore independent group assignments
source_idea: runtime reference probe during external-review implementation
---

# Independent significance permutations

Fresh measurement found compare([1,2,3,4], [2,3,4,5]) returns 0, while
independent exhaustive enumeration gives 32/70. Permuting one axis of a tiled
array applies the same assignment across every Monte Carlo draw.

Acceptance:

- Small problems enumerate unique index partitions exactly: the overlapping
  example gives 32/70, separated [1,2,3,4] vs [5,6,7,8] gives 2/70, equal means 1.
- Larger problems generate a new assignment per draw, are seeded/repeatable,
  and count the observed assignment so their p-value is never zero.
- The historical schema name bootstrap remains compatible; document that this
  significance test is a two-sided independent-sample permutation of mean gaps.
- All seven local gates pass and CI is verified after pushing.

Reference for randomized plus-one counting and exact partition enumeration:
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html
No SciPy dependency is introduced. Multiple-comparison adjustment remains spec 05.

## Verification

161 Node tests passed without skips; 60 Python tests passed. Exact answers
32/70, 2/70, and 1 matched; unequal-size absolute-tail examples gave 1/10
in either group order. Monte Carlo output was repeatable and nondegenerate,
and a separated large example gave 1/2001 rather than zero. All seven local
gates passed; existing baseline scripts are unchanged because none uses
significance. GitHub CI is checked on the pushed commit.
