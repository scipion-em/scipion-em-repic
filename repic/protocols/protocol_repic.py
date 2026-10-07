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
    OUTPUT_NAME = "Coordinates2D"
    _possibleOutputs = {OUTPUT_NAME: SetOfCoordinates}

    # -------------------------- DEFINE param functions ----------------------
    def __init__(self, **kwargs):
        ProtParticlePicking.__init__(self, **kwargs)
        self.pickedParticles = Integer(0)

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
                      label="Box size",  allowsPointers=True,
                      help='Particle box size')

        form.addParam('numParticles', params.IntParam, default=150,
                      expertLevel=params.LEVEL_ADVANCED,
                      label="Expected number of particles per micrograph",
                      help='Expected number of particles per micrograph')


    # --------------------------- STEPS functions ------------------------------
    def _insertAllSteps(self):
        # Insert processing steps
        self._insertFunctionStep(self.convertInputStep)
        self._insertFunctionStep(self.getClicquesStep)
        self._insertFunctionStep(self.getOptimalClicquesStep)
        self._insertFunctionStep(self.createOutputStep)

    def convertInputStep(self):
        mics = self.getAllCoordsInputMicrographs()
        for micFn in mics:
            coordsInMic, mic = [], mics[micFn]
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
        os.makedirs(outCoords, exist_ok=True)
        boxsize = self.boxsize.get()
        args = ' %s %s %i ' % (self._getExtraPath(), outCoords, boxsize)
        Plugin.runRepic(self, 'get_cliques', args)

    def getOptimalClicquesStep(self):
        outputOfCliques = self._getExtraPath('output')
        args = ' --num_particles %i %s %i' % (self.numParticles.get(), outputOfCliques, self.boxsize.get())
        Plugin.runRepic(self, 'run_ilp', args)

    def createOutputStep(self):
        pickedParticles = 0
        outputSet = SetOfCoordinates.create(outputPath=self.getPath(),
                                            prefix="coordinates")
        # Copy info from the first coordinates set
        firstInputSet = self.inputCoordinates[0].get()
        outputSet.setBoxSize(self.boxsize.get())
        outputSet.setMicrographs(firstInputSet._micrographsPointer)
        mics = self.getAllCoordsInputMicrographs()

        for micFn in mics:
            coord = Coordinate()
            coordsInMic, mic = [], mics[micFn]
            dirName = self._getExtraPath('output')
            fn = self.getMicBoxFile(dirName, micFn)

            if not os.path.exists(fn):
                # A micrograph REPIC produced nothing for has no file at
                # all. That is an empty result, not a reason to lose
                # every other micrograph's particles.
                self.info("No REPIC output for %s; no particles from it."
                          % micFn)
                continue

            if os.path.getsize(fn) > 0:
                with open(fn, 'r') as f:
                    lines = f.readlines()
                    for line in lines:
                        line = line.strip().split()
                        coord.setMicrograph(mic)
                        coord.setObjId(None)
                        coord.setX(int(line[0]))
                        coord.setY(int(line[1]))
                        outputSet.append(coord)
                        pickedParticles += 1

        # Keep the count on the protocol: _summary runs in a later process
        # and used to read a class attribute nobody ever assigned, so it
        # always reported zero particles.
        self.pickedParticles.set(pickedParticles)
        self._store(self.pickedParticles)

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
          micFn = self.getMicKey(mic)
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

    def getMicBoxFile(self, dirName, micKey):
      """Box file of one micrograph, under the name it was written with.

      A run started before the keys carried the micrograph id wrote the
      plain file name, and those box files are its results: when only
      that one is on disk it is still the one read, so continuing such a
      run keeps working.
      """
      scoped = os.path.join(dirName, micKey + '.box')

      if not os.path.exists(scoped):
        legacy = os.path.join(dirName, self.stripMicKeyScope(micKey) + '.box')

        if os.path.exists(legacy):
          return legacy

      return scoped

    @staticmethod
    def stripMicKeyScope(micKey):
      """The plain file name a key was built from."""
      prefix, sep, rest = micKey.partition('__')

      return rest if sep and prefix.isdigit() else micKey

    def getMicKey(self, mic):
      """The name this micrograph is known by, and that names its files.

      A Set can hold two micrographs whose files differ only in their
      directory. Keyed on the file name alone one of them is simply
      dropped from the dictionary - never picked, with the other's
      coordinates written into what should have been its box file. The
      id keeps them apart; the file name stays in the key so the box
      files remain readable.
      """
      return '%06d__%s' % (mic.getObjId(),
                           self.prunePaths([mic.getFileName()])[0])

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
            summary.append("REPIC protocol has found *%i* particles."
                           % self.pickedParticles.get(0))
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