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
