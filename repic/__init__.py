# **************************************************************************
# *
# * Authors:     J.L Vilas (jlvilas@cnb.csic.es)
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
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************

import os

import pwem
from pyworkflow.utils import Environ
from repic.constants import *

__version__ = '3.0.0'
_logo = "icon.png"
_references = ['cameron2023']


class Plugin(pwem.Plugin):
    _url = 'https://github.com/scipion-em/scipion-em-repic'

    @classmethod
    def _defineVariables(cls):
        # repic does NOT need EmVar because it uses a conda environment.
        cls._defineVar(REPIC_ENV_ACTIVATION, DEFAULT_ACTIVATION_CMD)


    @classmethod
    def getRepicEnvActivation(cls):
        return cls.getVar(REPIC_ENV_ACTIVATION)

    @classmethod
    def getEnviron(cls, gpuId='0'):
        """ Setup the environment variables needed to launch Repic. """
        environ = Environ(os.environ)
        if 'PYTHONPATH' in environ:
            # this is required for python virtual env to work
            del environ['PYTHONPATH']
        environ.update({'PYTHONPATH': cls.getHome("REPIC")},
                       position=Environ.BEGIN)
        return environ

    @classmethod
    def defineBinaries(cls, env):
        REPIC_INSTALLED = '%s-installed' % REPIC_ENV_NAME

        # try to get CONDA activation command
        installationCmd = cls.getCondaActivationCmd()

        # Create the environment
        installationCmd += 'conda create -n %s python=3.9 -y && ' % REPIC_ENV_NAME
        installationCmd += 'conda activate %s && ' % REPIC_ENV_NAME
        installationCmd += 'pip install git+https://github.com/ccameron/REPIC.git@v%s && ' % VERSION

        installationCmd += 'touch %s' % REPIC_INSTALLED

        repic_commands = [(installationCmd, REPIC_INSTALLED)]

        envPath = os.environ.get('PATH', "")  # keep path since conda likely in there
        installEnvVars = {'PATH': envPath} if envPath else None

        env.addPackage(REPIC,
                       version=VERSION,
                       tar='void.tgz',
                       commands=repic_commands,
                       neededProgs=cls.getDependencies(),
                       vars=installEnvVars,
                       default=bool(cls.getCondaActivationCmd()))

    @classmethod
    def getActivationCmd(cls):
        """ Return the activation command. """
        return '%s %s' % (cls.getCondaActivationCmd(),
                          cls.getRepicEnvActivation())

    @classmethod
    def getDependencies(cls):
        # try to get CONDA activation command
        condaActivationCmd = cls.getCondaActivationCmd()
        neededProgs = []
        if not condaActivationCmd:
            neededProgs.append('conda')

        return neededProgs

    @classmethod
    def runRepic(cls, protocol, program, args, cwd=None):
        """ Run repic command from a given protocol. """

        mycmd = f'{cls.getActivationCmd()} && '
        mycmd += 'repic %s '% program

        protocol.runJob(mycmd, args, env=cls.getEnviron(), cwd=cwd)
