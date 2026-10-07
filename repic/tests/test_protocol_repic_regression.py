# **************************************************************************
# *
# * Regression tests for the REPIC consensus protocol.
# *
# * These run without Scipion data: they exercise the protocol's own logic
# * with light doubles.
# *
# **************************************************************************

import os
import tempfile
import unittest

from repic.protocols.protocol_repic import ProtRepic


class _Mic:
    def __init__(self, fileName, objId=1):
        self._fileName = fileName
        self._objId = objId

    def getObjId(self):
        return self._objId

    def getFileName(self):
        return self._fileName

    def clone(self):
        return _Mic(self._fileName, self._objId)


class _Value:
    def __init__(self, value):
        self._value = value

    def get(self, default=None):
        return self._value

    def set(self, value):
        self._value = value


class _OutputCoords:
    def __init__(self):
        self.appended = []

    def setBoxSize(self, boxSize):
        self.boxSize = boxSize

    def setMicrographs(self, mics):
        self.mics = mics

    def append(self, coord):
        self.appended.append((coord.getX(), coord.getY()))


class _CoordInput:
    def __init__(self, mics):
        self._mics = mics
        self._micrographsPointer = object()

    def get(self):
        return self

    def getMicrographs(self):
        return self._mics


class _OutputHarness(ProtRepic):
    def __init__(self, root, mics, boxSize=100):
        self._root = root
        self._mics = mics
        self.boxsize = _Value(boxSize)
        self.pickedParticles = _Value(0)
        self.inputCoordinates = [_CoordInput(mics)]
        self.outputs = {}
        self.stored = []

    def _getExtraPath(self, *parts):
        return os.path.join(self._root, 'extra', *parts)

    def getPath(self, *parts):
        return os.path.join(self._root, *parts)

    def _defineOutputs(self, **kwargs):
        self.outputs.update(kwargs)

    def _defineSourceRelation(self, *args):
        pass

    def _store(self, *args):
        self.stored.extend(args)

    def isFinished(self):
        return True

    def info(self, message):
        pass


class TestRepicParticleCount(unittest.TestCase):
    def testSummaryReportsTheParticlesActuallyWritten(self):
        # pickedParticles used to be a class attribute that nothing ever
        # assigned, so the summary always claimed zero particles however
        # many were written.
        with tempfile.TemporaryDirectory() as root:
            outDir = os.path.join(root, 'extra', 'output')
            os.makedirs(outDir)

            with open(os.path.join(outDir, 'mic_001.mrc.box'), 'w') as fh:
                fh.write("10 20 100 100 1\n30 40 100 100 1\n")

            mics = [_Mic('/data/mic_001.mrc')]
            protocol = _OutputHarness(root, mics)

            created = _OutputCoords()

            import repic.protocols.protocol_repic as module
            original = module.SetOfCoordinates
            module.SetOfCoordinates = type(
                '_Factory', (), {'create': staticmethod(
                    lambda outputPath, prefix: created)})

            try:
                ProtRepic.createOutputStep(protocol)
            finally:
                module.SetOfCoordinates = original

            self.assertEqual([(10, 20), (30, 40)], created.appended)
            self.assertEqual(2, protocol.pickedParticles.get())

            summary = ProtRepic._summary(protocol)
            self.assertTrue(
                any("*2* particles" in line for line in summary),
                "The summary must report what was really written: %s" % summary,
            )


class _CliquesHarness(ProtRepic):
    def __init__(self, root):
        self._root = root
        self.boxsize = _Value(100)
        self.runs = []

    def _getExtraPath(self, *parts):
        return os.path.join(self._root, 'extra', *parts)


class TestRepicRetriedStep(unittest.TestCase):
    def testCliquesStepCanRunAgainOverAnExistingFolder(self):
        # A step that is retried after a failure found its output folder
        # already there and died on mkdir instead of carrying on.
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'extra', 'output'))
            protocol = _CliquesHarness(root)

            calls = []

            import repic.protocols.protocol_repic as module
            original = module.Plugin
            module.Plugin = type('_Plugin', (), {'runRepic': staticmethod(
                lambda prot, program, args: calls.append(program))})

            try:
                ProtRepic.getClicquesStep(protocol)
            finally:
                module.Plugin = original

            self.assertEqual(['get_cliques'], calls)


class TestRepicHasNoSharedMutableState(unittest.TestCase):
    def testTheClassCarriesNoMutableAttributes(self):
        # micList was a list on the class, so every instance in the same
        # process appended to the same one.
        for name in ('micList', 'pickedParticles'):
            value = ProtRepic.__dict__.get(name)
            self.assertNotIsInstance(
                value, (list, dict, set),
                "%s must not be a mutable attribute shared by every "
                "instance of the protocol." % name,
            )


if __name__ == "__main__":
    unittest.main()


SAME_BASENAME_A = '/data/sessionA/mic001.mrc'
SAME_BASENAME_B = '/data/sessionB/mic001.mrc'


class _MicSet:
    def __init__(self, mics):
        self._mics = list(mics)

    def __iter__(self):
        return iter(self._mics)


class _CoordSetWithMics:
    def __init__(self, mics):
        self._mics = _MicSet(mics)

    def get(self):
        return self

    def getMicrographs(self):
        return self._mics


class _MicrographsHarness(ProtRepic):
    def __init__(self, coordInputs):
        self.inputCoordinates = coordInputs


class TestRepicKeepsTwoMicrographsApart(unittest.TestCase):
    """The input micrographs are collected into a dict keyed by the
    name of their file.

    A Set can hold /data/sessionA/mic001.mrc and /data/sessionB/mic001.mrc
    at once: different micrographs, one basename. Keyed on that alone one
    of them simply disappears, and the box file written for it is the
    other's.
    """

    def _harness(self):
        mics = [_Mic(SAME_BASENAME_A, objId=1),
                _Mic(SAME_BASENAME_B, objId=2)]

        return _MicrographsHarness([_CoordSetWithMics(mics)])

    def testBothMicrographsSurviveTheCollection(self):
        harness = self._harness()

        mics = harness.getAllCoordsInputMicrographs()

        self.assertEqual(
            len(mics),
            2,
            "One micrograph was dropped: it is never picked, and its "
            "box file holds the other micrograph's coordinates.",
        )

    def testEachKeyStillPointsAtItsOwnMicrograph(self):
        harness = self._harness()

        mics = harness.getAllCoordsInputMicrographs()

        byId = {mic.getObjId(): key for key, mic in mics.items()}

        self.assertEqual(
            len(byId),
            2,
            "Two keys must not resolve to the same micrograph.",
        )

    def testTheKeyStaysRecognisable(self):
        """It names the box files, so it has to stay readable."""
        harness = self._harness()

        for key in harness.getAllCoordsInputMicrographs():
            self.assertIn('mic001', key)

    def testMicrographsWithDistinctNamesAreUnaffected(self):
        mics = [_Mic('/data/mic001.mrc', objId=1),
                _Mic('/data/mic002.mrc', objId=2)]
        harness = _MicrographsHarness([_CoordSetWithMics(mics)])

        self.assertEqual(len(harness.getAllCoordsInputMicrographs()), 2)

    def testTheIntersectionAcrossPickersStillWorks(self):
        """With several pickers only the shared micrographs are kept."""
        first = [_Mic('/data/mic001.mrc', objId=1),
                 _Mic('/data/mic002.mrc', objId=2)]
        second = [_Mic('/data/mic001.mrc', objId=1)]
        harness = _MicrographsHarness(
            [_CoordSetWithMics(first), _CoordSetWithMics(second)])

        mics = harness.getAllCoordsInputMicrographs()

        self.assertEqual(
            [mic.getObjId() for mic in mics.values()],
            [1],
            "Only the micrograph both pickers saw may go through.",
        )


class TestRepicReadsBackWhatItWrote(unittest.TestCase):
    """The box files are read back under the key they were written with,
    and a run started before the keys carried the id wrote the plain
    name."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.harness = _MicrographsHarness([])

    def _write(self, name):
        path = os.path.join(self.root, name + '.box')
        with open(path, 'w') as handle:
            handle.write('')
        return path

    def testTheScopedFileIsUsedWhenThisRunWroteIt(self):
        scoped = self._write('000001__mic001.mrc')

        self.assertEqual(
            self.harness.getMicBoxFile(self.root, '000001__mic001.mrc'),
            scoped,
        )

    def testAnOlderRunsBoxFileIsStillFound(self):
        legacy = self._write('mic001.mrc')

        self.assertEqual(
            self.harness.getMicBoxFile(self.root, '000001__mic001.mrc'),
            legacy,
            "The box files an interrupted run already produced are its "
            "results; continuing it must keep reading them.",
        )

    def testTheScopedFileWinsOverTheOlderOne(self):
        self._write('mic001.mrc')
        scoped = self._write('000001__mic001.mrc')

        self.assertEqual(
            self.harness.getMicBoxFile(self.root, '000001__mic001.mrc'),
            scoped,
        )

    def testAKeyWithoutAScopeIsLeftAlone(self):
        self.assertEqual(
            ProtRepic.stripMicKeyScope('mic001.mrc'), 'mic001.mrc')

    def testAnUnderscoreInTheNameIsNotMistakenForAScope(self):
        self.assertEqual(
            ProtRepic.stripMicKeyScope('my__movie.mrc'), 'my__movie.mrc')


class TestRepicToleratesAMicrographWithoutOutput(unittest.TestCase):
    """REPIC writes nothing at all for a micrograph it found no
    consensus particles in."""

    def testTheOtherMicrographsParticlesAreStillCollected(self):
        with tempfile.TemporaryDirectory() as root:
            outDir = os.path.join(root, 'extra', 'output')
            os.makedirs(outDir)

            mics = [_Mic('/data/mic_001.mrc', objId=1),
                    _Mic('/data/mic_002.mrc', objId=2)]
            protocol = _OutputHarness(root, mics)

            # Only the second micrograph produced anything.
            key = protocol.getMicKey(mics[1])
            with open(os.path.join(outDir, key + '.box'), 'w') as fh:
                fh.write("10 20 100 100 1\n")

            created = _OutputCoords()

            import repic.protocols.protocol_repic as module
            original = module.SetOfCoordinates
            module.SetOfCoordinates = type(
                '_Factory', (), {'create': staticmethod(
                    lambda outputPath, prefix: created)})

            try:
                ProtRepic.createOutputStep(protocol)
            finally:
                module.SetOfCoordinates = original

            self.assertEqual(
                [(10, 20)],
                created.appended,
                "A micrograph REPIC produced nothing for must not cost "
                "every other micrograph its particles.",
            )
