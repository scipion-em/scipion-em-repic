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
from tomo.objects import SetOfCoordinates3D, Coordinate3D
import pyworkflow.utils.path as path
from pyworkflow.utils import getFiles, removeBaseExt, moveFile
from repic import Plugin
import tomo.constants as const


class ProtRepicTomo(ProtParticlePicking):
    """
    This protocol performs a consensus picking. Given several sets of coordinates picked with different
    algorithms, Repic will find a reliable consensus set of coordinates. Usually, it works in an iterative
    manner. The consensus set is used to train the pickers again, and repic is used to find a greater
    consensus set, thus iteratively, this process converges to the true set of particles.
    """
    _label = 'oneshot tomo picking consensus'
    micList = []
    pickedParticles = 0
    OUTPUT_NAME = "outputSetOfCoordinates3D"
    #_possibleOutputs = {outputSetOfCoordinates3D: SetOfCoordinates3D}

    # -------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        """ Define the input parameters that will be used.
        Params:
            form: this is the form to be populated with sections and params.
        """
        # You need a params to belong to a section:
        form.addSection(label=Message.LABEL_INPUT)
        form.addParam('inputCoordinates', params.MultiPointerParam,
                      pointerClass='SetOfCoordinates3D',
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
        mics = self.getAllCoordsInputTomograms()
        for micFn in mics:
            coordsInMic, mic = [], mics[micFn]
            self.micList.append(micFn)
            pickerNum = 0
            for coordSet in self.inputCoordinates:
                folderName = 'picker_%i' % pickerNum
                dirName = self._getExtraPath(folderName)
                path.makePath(dirName)
                fn = os.path.join(dirName, micFn + '.box')
                with open(fn, 'w') as f:
                    for coord in coordSet.get().iterCoordinates(mic):
                        line = '%i %i %i %i %i %i 1 ' % (coord.getX(const.BOTTOM_LEFT_CORNER),
                                                         coord.getY(const.BOTTOM_LEFT_CORNER),
                                                         coord.getZ(const.BOTTOM_LEFT_CORNER),
                                                         self.boxsize.get(),
                                                         self.boxsize.get(), self.boxsize.get())
                        f.write(line + '\n')

                        coordsInMic.append(coord)
                    f.close()
                    pickerNum = pickerNum + 1

    def getClicquesStep(self):
        outCoords = self._getExtraPath('repicOutput')
        os.mkdir(outCoords)
        boxsize = self.boxsize.get()
        args = ' %s %s %i ' % (self._getExtraPath(), outCoords, boxsize)
        Plugin.runRepic(self, 'get_cliques.py', args)

    def getOptimalClicquesStep(self):
        outputOfCliques = self._getExtraPath('repicOutput')
        args = ' --num_particles %i %s %i' % (self.numParticles.get(), outputOfCliques, self.boxsize.get())
        Plugin.runRepic(self, 'run_ilp.py', args)

    def createOutputStep(self):

        outputSet = SetOfCoordinates3D.create(outputPath=self.getPath(), prefix="coordinates.sqlite")
        # Copy info from the first coordinates set
        tomos = self.inputCoordinates[0].get().getPrecedents()
        sampling = self.inputCoordinates[0].get().getSamplingRate()
        outputSet.setBoxSize(self.boxsize.get())
        outputSet.setPrecedents(tomos)
        outputSet.setSamplingRate(sampling)
        mics = self.getAllCoordsInputTomograms()

        for micFn in mics:
            coord = Coordinate3D()
            coordsInMic, mic = [], mics[micFn]
            dirName = self._getExtraPath('repicOutput')
            fn = os.path.join(dirName, micFn + '.box')
            if os.path.getsize(fn) > 0:
                with open(fn, 'r') as f:
                    lines = f.readlines()
                    for line in lines:
                        coord.setObjId(None)

                        for t in tomos.iterItems():
                            tsId = t.getTsId()
                            if tsId == micFn:
                                coord.setVolume(t)
                                break
                        line = line.split()
                        coord.setTomoId(micFn)
                        coord.setX(int(line[0]), const.BOTTOM_LEFT_CORNER)
                        coord.setY(int(line[1]), const.BOTTOM_LEFT_CORNER)
                        coord.setZ(int(line[2]), const.BOTTOM_LEFT_CORNER)

                        outputSet.append(coord)
                        outputSet.update(coord)

        outputSet.write()

        self._defineOutputs(outputSetOfCoordinates3D=outputSet)

        self._defineSourceRelation(self.inputCoordinates, outputSet)
        self._store()

        # for inset in self.inputCoordinates:
        #    self._defineSourceRelation(inset.get(), outputSet)

    def getAllCoordsInputTomograms(self):
        '''Returns a dic {micFn: mic} with the input micrographs present associated with all the input coordinates sets.
      If shared, the list contains only those micrographs present in all input coordinates sets, else the list contains
      all microgrpah present in any set (Intersection vs Union)
      Do not create a set, because of concurrency in the database'''
        micDict, micFns = {}, set([])
        for inputCoord in self.inputCoordinates:
            newTomos = inputCoord.get().getPrecedents()
            newTomosFns = []
            for tomo in newTomos:
                #micFn = self.prunePaths([tomo.getFileName()])[0]
                micFn = tomo.getTsId()
                micDict[micFn] = tomo.clone()
                newTomosFns.append(micFn)

            if micFns == set([]):
                micFns = micFns | set(newTomosFns)
            else:
                micFns = micFns & set(newTomosFns)

        sharedTomoDict = {}

        for micFn in micFns:
            sharedTomoDict[micFn] = micDict[micFn]

        return sharedTomoDict

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
