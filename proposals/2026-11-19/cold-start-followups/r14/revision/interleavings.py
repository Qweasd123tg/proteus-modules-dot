"""Deterministic design oracle, NOT a Proteus implementation or a performance test.
Enumerate interleavings of an opening publisher, a real writer+completion path
(modelled by acknowledgements), and two reading clients. A strict validation
has already produced R0. No storage, serialization or backend is substituted
in an application; correct results here do not qualify a backend.
"""
from collections import Counter
from itertools import permutations
from types import MappingProxyType
import unittest

# Stable source identity here stands in for (authority, locator, revision, SHA).
A = ("worker-A", "inc-1", 100, "sha-A")
B = ("worker-A", "inc-1", 102, "sha-B")
ALIEN = ("worker-A", "inc-2", 100, "sha-A")
# A single owned archive; checked independent delta; never relabel one as the other.
ARCHIVE = tuple(range(100))
SUFFIX = (100, 101)
EXPECTED = MappingProxyType({A: ARCHIVE, B: ARCHIVE + SUFFIX})

class Ready:
    def __init__(self):
        self.pin = {A: (ARCHIVE, ())}
        self.source = A
        self.active = A
        self.head = None
        self.named = set()
        self.owner = A
        self.job = A
        self.alive = True
        self.capturing = False
        self.c = Counter(full_render=1)
        self.errors = []

    def step(self, event, fault=False):
        if event == 'C':  # Writer-authorized commit advances source BEFORE UI settles.
            self.c['lease_resume'] += 1
            self.source = B
            self.capturing = True
        elif event == 'S':  # Move checked suffix into a view of the identical base.
            assert self.capturing and self.source == B
            self.capturing = False
            self.pin[B] = (self.pin[A][0], SUFFIX)
            self.active = self.owner = B
        elif event == 'N':  # Write immutable named R0 header, after payloads (not shown).
            if self.alive and not fault and self.source == self.job == self.owner:
                self.named.add(self.job)
        elif event == 'H':  # stale completion cannot mutate or clear R1.
            if (self.alive and not fault and self.job in self.named
                    and self.source == self.job == self.owner):
                self.head = self.job
        elif event == 'P':  # R0 cursor from the first snapshot: exactly the older 50
            assert self.page(A, 50) == ARCHIVE[:50]
        elif event == 'E':  # Before completion export current visible revision; never mix.
            s = self.active
            assert self.export(s) == EXPECTED[s]
        elif event == 'L':
            if self.active != self.source:
                # A latest endpoint can't treat R0 as current while a turn writes R1.
                assert self.latest() is None
            else:
                assert self.latest() == EXPECTED[self.source][-50:]
        else:
            raise AssertionError(event)

    def length(self, segments):
        return sum(map(len, segments))

    def page(self, s, before):
        if not self.alive or s not in self.pin:
            raise LookupError('not this revision / unavailable')
        segments = self.pin[s]
        if not 0 <= before <= self.length(segments):
            raise IndexError('outside revision')
        lo, hi = max(before - 50, 0), before
        out = ()
        for part in segments:
            out += part[max(0, lo):max(0, hi)]
            lo -= len(part)
            hi -= len(part)
        return out

    def export(self, s):
        if not self.alive or s not in self.pin:
            raise LookupError()
        return tuple(row for segment in self.pin[s] for row in segment)

    def latest(self, change_after_read=None):
        # Integration uses a real current source lookup, not UI active marker.
        s = self.source
        if not self.alive or s not in self.pin:
            return None
        page = self.page(s, self.length(self.pin[s]))
        if change_after_read is not None:
            self.source = change_after_read
        return page if s == self.source else None

    def close(self):
        self.alive = False
        self.owner = None
        self.pin.clear()

def schedules():
    for schedule in permutations('CSNHPEL'):
        if schedule.index('C') < schedule.index('S') and schedule.index('N') < schedule.index('H'):
            yield schedule

class Races(unittest.TestCase):
    def test_all_1260_schedules_with_and_without_cache_fault(self):
        n = 0
        for fault in (False, True):
            for schedule in schedules():
                r = Ready()
                for event in schedule:
                    r.step(event, fault)
                self.assertIs(r.pin[A][0], r.pin[B][0])
                self.assertEqual(r.c, Counter(full_render=1, lease_resume=1))
                self.assertEqual(r.page(B, 101), EXPECTED[B][51:101])
                self.assertNotEqual(r.head, B)  # old publisher had no right to produce B
                if fault or schedule.index("C") < schedule.index("H"):
                    self.assertIsNone(r.head)
                else:
                    self.assertEqual(r.head, A)  # stale *existing* HEAD is not authority
                    self.assertEqual(r.latest(), EXPECTED[B][-50:])
                n += 1
        self.assertEqual(n, 2520)

    def test_cancel_at_every_boundary(self):
        for events in ((), ('N',), ('C','S','N')):
            r = Ready()
            for e in events:
                r.step(e)
            r.close()
            old = set(r.named), r.head
            r.step('N'); r.step('H')
            self.assertEqual((r.named, r.head), old)
            with self.assertRaises(LookupError):
                r.page(A, 50)
            self.assertIsNone(r.latest())

    def test_latest_replacement_after_copy_does_not_relabel_and_named_is_scoped(self):
        r = Ready()
        self.assertIsNone(r.latest(change_after_read=ALIEN))
        self.assertIsNone(r.latest())
        with self.assertRaises(LookupError):
            r.page(ALIEN, 50)
        # Already-held OLD incarnation can still finish a pinned private read;
        # the route for a replacement must never be handed this old handle.
        self.assertEqual(r.page(A,100),ARCHIVE[50:])

    def test_invalid_bounds_not_a_cache_miss(self):
        r = Ready()
        for b in (-1, 101, 2**64):
            with self.assertRaises(IndexError):
                r.page(A,b)
        for b in range(len(ARCHIVE)+1):
            self.assertEqual(r.page(A,b),ARCHIVE[max(b-50,0):b])

    def test_mutation_kills_naive_spawn_only_or_erase_on_failed_publish(self):
        r = Ready()
        r.step('C'); r.pin.pop(A)
        with self.assertRaises(LookupError):
            r.page(A,50)
        with self.assertRaises(KeyError):
            r.step('S')  # no substrate for certified suffix even with an exact ACK
        r = Ready(); r.step('N'); r.step('C'); r.step('S')
        r.head = r.job  # hypothetical unconditional stale write
        self.assertNotEqual(r.head,r.owner)

if __name__ == '__main__':
    unittest.main(verbosity=2)
