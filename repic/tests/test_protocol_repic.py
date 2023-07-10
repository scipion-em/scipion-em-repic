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
        protImpMics = cls._runInportMicrographs()
        inCoords = []
        protImpCoords1 = cls._runImportCoordinates(protImpMics)
        point = Pointer(protImpCoords1, extended="outputCoordinates")
        inCoords.append(point)
        protImpCoords2 = cls._runImportCoordinates(protImpMics)
        point = Pointer(protImpCoords2, extended="outputCoordinates")
        inCoords.append(point)
        protImpCoords3 = cls._runImportCoordinates(protImpMics)
        point = Pointer(protImpCoords3, extended="outputCoordinates")
        inCoords.append(point)
        cls.protRepic = cls._runRepicConsensus(inCoords)

    @classmethod
    def _runInportMicrographs(cls):
        protImport = cls.newProtocol(ProtImportMicrographs,
                                     filesPath=cls.dsRepic.getFile('allMics'),
                                     samplingRate=1.237, voltage=300)
        protImport.setObjLabel('Import micrographs')
        cls.launchProtocol(protImport)
        cls.assertIsNotNone(protImport.outputMicrographs.getFileName(),
                            "There was a problem with the import")
        return protImport

    @classmethod
    def _runImportCoordinates(cls, protImportMics):
        prot = cls.newProtocol(ProtImportCoordinates,
                               importFrom=ProtImportCoordinates.IMPORT_FROM_XMIPP,
                               filesPath=cls.dsRepic.getFile('autoPickingCoordinates'),
                               filesPattern='*.pos', boxSize=150,
                               scale=1.,
                               invertX=False,
                               invertY=False
                               )
        prot.inputMicrographs.set(protImportMics.outputMicrographs)
        prot.setObjLabel('Import coords')
        cls.launchProtocol(prot)
        cls.assertIsNotNone(prot.outputCoordinates, "There was a problem with the import")
        return prot

    @classmethod
    def _runRepicConsensus(cls, inpCoords):
        prot = cls.newProtocol(ProtRepic,
                               inputCoordinates=inpCoords,
                               boxsize=150,
                               numParticles=100)

        prot.setObjLabel('Repic picking')
        cls.launchProtocol(prot)
        return prot

    def test_RepicConsensus(self):
        self.assertIsNotNone(self.protRepic.outputCoordinates,
                             "There was a problem with the consensus")


