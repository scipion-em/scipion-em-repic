# ***************************************************************************
# *
# * Authors:     J.L. Vilas (jlvilas@cnb.csic.es)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# ***************************************************************************

from pyworkflow.tests import BaseTest, DataSet
import pyworkflow.tests as tests
from pyworkflow.object import Pointer

from pwem.protocols import (ProtImportMicrographs, ProtImportCoordinates)
from repic.protocols import ProtRepic


class TestRepic(BaseTest):
    @classmethod
    def setUpClass(cls):
        tests.setupTestProject(cls)
        cls.dsRepic = DataSet.getDataSet('deepConsensusPicking')

    def _runInportMicrographs(self):
        protImport = self.newProtocol(ProtImportMicrographs,
                                      filesPath=self.dsRepic.getFile('allMics'),
                                      samplingRate=1.237, voltage=300)
        protImport.setObjLabel('Import micrographs')
        self.launchProtocol(protImport)
        self.assertIsNotNone(protImport.outputMicrographs.getFileName(),
                             "There was a problem with the import")
        return protImport

    def _runImportCoordinates(self, protImportMics):
        prot = self.newProtocol(ProtImportCoordinates,
                                importFrom=ProtImportCoordinates.IMPORT_FROM_XMIPP,
                                filesPath=self.dsRepic.getFile('autoPickingCoordinates'),
                                filesPattern='*.pos', boxSize=150,
                                scale=1.,
                                invertX=False,
                                invertY=False
                                )
        prot.inputMicrographs.set(protImportMics.outputMicrographs)
        prot.setObjLabel('Import coords')
        self.launchProtocol(prot)
        self.assertIsNotNone(prot.outputCoordinates, "There was a problem with the import")
        return prot

    def _runRepicConsensus(self, inpCoords):
        prot = self.newProtocol(ProtRepic,
                                inputCoordinates=inpCoords,
                                boxsize = 150,
                                numParticles = 100)

        prot.setObjLabel('Repic picking')
        self.launchProtocol(prot)
        self.assertIsNotNone(prot.outputCoordinates,
                             "There was a problem with the consensus")
        self.assertIsNotNone(prot.outputParticles,
                             "There was a problem with the consensus")
        return prot

    def testRepicConsensus(self):
        inpCoords = self.prepareInput()
        self.lastRun = self._runRepicConsensus(inpCoords)

    def prepareInput(self):
        protImpMics = self._runInportMicrographs()
        protImpCoords = self._runImportCoordinates(protImpMics)

        inpCoords = []
        for prot in protImpCoords:
            point = Pointer(prot, extended="outputCoordinates")
            inpCoords.append(point)
        return inpCoords
