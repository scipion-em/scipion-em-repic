# -*- coding: utf-8 -*-
# **************************************************************************
# *
# * Authors:     J.L. Vilas (jlvilas@cnb.csic.es)
# *
# * your institution
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
# *  e-mail address 'you@yourinstitution.email'
# *
# **************************************************************************


"""
Describe your python module here:
This module will provide the traditional Hello world example
"""
import os

from pyworkflow.protocol import Protocol, params, Integer
from pwem.protocols import ProtParticlePicking
from pyworkflow.utils import Message
from pwem.objects import SetOfCoordinates, Coordinate
from pyworkflow.utils import getFiles, removeBaseExt, moveFile
from repic import Plugin


class ProtRepic(ProtParticlePicking):
    """
    This protocol performs a consensus picking. Given several sets of coordinates picked with different
    algorithms, Repic will find a reliable consensus set of coordinates. Usually, it works in an iterative
    manner. The consensus set is used to train the pickers again, and repic is used to find a greater
    consensus set, thus iteratively, this process converges to the true set of particles.
    """
    _label = 'oneshot picking consensus'
    micList = []
    pickedParticles = 0
    OUTPUT_NAME = "Coordinates2D"
    _possibleOutputs = {OUTPUT_NAME: SetOfCoordinates}

    # -------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        """ Define the input parameters that will be used.
        Params:
            form: this is the form to be populated with sections and params.
        """
        # You need a params to belong to a section:
        form.addSection(label=Message.LABEL_INPUT)
        form.addParam('inputCoordinates', params.MultiPointerParam,
                      pointerClass='SetOfCoordinates',
                      label="Input coordinates", important=True,
                      help='Select the set of coordinates to compare')

        form.addParam('boxsize', params.IntParam, default=100,
                      label="Box size",
                      help='Particle box size')

        form.addParam('numParticles', params.IntParam, default=150,
                      expertLevel=params.LEVEL_ADVANCED,
                      label="Expected number of particles per micrograph",
                      help='Expected number of particles per micrograph')


    # --------------------------- STEPS functions ------------------------------
    def _insertAllSteps(self):
        self.checkedMics = set()  # those mics ready to be processed (micId)
        self.processedMics = set()  # those mics already processed (micId)
        self.sampligRates = []

        # Insert processing steps
        self._insertFunctionStep(self.convertInputStep)
        self._insertFunctionStep(self.getClicquesStep)
        self._insertFunctionStep(self.getOptimalClicquesStep)
        self._insertFunctionStep(self.createOutputStep)

    def convertInputStep(self):
        mics = self.getAllCoordsInputMicrographs()
        for micFn in mics:
            coordsInMic, mic = [], mics[micFn]
            self.micList.append(micFn)
            pickerNum = 0
            for coordSet in self.inputCoordinates:
                folderName = 'picker_%i' % pickerNum
                dirName = self._getExtraPath(folderName)
                if not os.path.exists(dirName):
                    os.mkdir(dirName)
                fn = os.path.join(dirName, micFn + '.box')
                with open(fn, 'w') as f:
                    for coord in coordSet.get().iterCoordinates(mic):
                        line = '%i %i %i %i 1 ' % (coord.getX(), coord.getY(), self.boxsize.get(), self.boxsize.get())
                        f.write(line + '\n')

                        coordsInMic.append(coord)
                    f.close()
                    pickerNum = pickerNum + 1

    def getClicquesStep(self):
        outCoords = self._getExtraPath('output')
        os.mkdir(outCoords)
        boxsize = self.boxsize.get()
        args = ' %s %s %i ' % (self._getExtraPath(), outCoords, boxsize)
        Plugin.runRepic(self, 'get_cliques', args)

    def getOptimalClicquesStep(self):
        outputOfCliques = self._getExtraPath('output')
        args = ' --num_particles %i %s %i' % (self.numParticles.get(), outputOfCliques, self.boxsize.get())
        Plugin.runRepic(self, 'run_ilp', args)

    def createOutputStep(self):

        outputSet = SetOfCoordinates.create(outputPath=self.getPath(), prefix="coordinates.sqlite")
        # Copy info from the first coordinates set
        firstInputSet = self.inputCoordinates[0].get()
        outputSet.setBoxSize(self.boxsize.get())
        outputSet.setMicrographs(firstInputSet._micrographsPointer)
        mics = self.getAllCoordsInputMicrographs()

        for micFn in mics:
            coord = Coordinate()
            coordsInMic, mic = [], mics[micFn]
            dirName = self._getExtraPath('output')
            fn = os.path.join(dirName, micFn + '.box')
            if os.path.getsize(fn) > 0:
                with open(fn, 'r') as f:
                    lines = f.readlines()
                    for line in lines:
                        coord.setMicrograph(mic)
                        coord.setObjId(None)
                        coord.setX(int(line[0]))
                        coord.setY(int(line[1]))
                        outputSet.append(coord)

        self._defineOutputs(**{self.OUTPUT_NAME:outputSet})
        for inset in self.inputCoordinates:
            self._defineSourceRelation(inset.get(), outputSet)


    def getAllCoordsInputMicrographs(self):
      '''Returns a dic {micFn: mic} with the input micrographs present associated with all the input coordinates sets.
      If shared, the list contains only those micrographs present in all input coordinates sets, else the list contains
      all microgrpah present in any set (Intersection vs Union)
      Do not create a set, because of concurrency in the database'''
      micDict, micFns = {}, set([])
      for inputCoord in self.inputCoordinates:
        newMics = inputCoord.get().getMicrographs()
        newMicFns = []
        for mic in newMics:
          micFn = self.prunePaths([mic.getFileName()])[0]
          micDict[micFn] = mic.clone()
          newMicFns.append(micFn)

        if micFns == set([]):
          micFns = micFns | set(newMicFns)
        else:
          micFns = micFns & set(newMicFns)

      sharedMicDict = {}

      for micFn in micFns:
        sharedMicDict[micFn] = micDict[micFn]


      return sharedMicDict

    def prunePaths(self, paths):
      fns = []
      for path in paths:
        fns.append(path.split('/')[-1])
      return fns

    # --------------------------- INFO functions -----------------------------------
    def _summary(self):
        """ Summarize what the protocol has done"""
        summary = []

        if self.isFinished():
            summary.append("REPIC protocol has found *%i* particles." % (self.pickedParticles))
        return summary

    def _methods(self):
        methods = []

        if self.isFinished():
            methods.append("%s has been printed in this run %i times." % (self.message, self.times))
            if self.previousCount.hasPointer():
                methods.append("Accumulated count from previous runs were %i."
                               " In total, %s messages has been printed."
                               % (self.previousCount, self.count))
        return methods

'''
class repicNumParticles(Wizard):
    _targets = [(ProtRepic, ['numParticles'])]
    def show(self, form):
'''