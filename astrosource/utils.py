import numpy as np
import os
import shutil
import click

class Mutex(click.Option):
    def __init__(self, *args, **kwargs):
        self.not_required_if:list = kwargs.pop("not_required_if")

        assert self.not_required_if, "'not_required_if' parameter required"
        kwargs["help"] = (kwargs.get("help", "") + "Option is mutually exclusive with " + ", ".join(self.not_required_if) + ".").strip()
        super(Mutex, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        current_opt:bool = self.name in opts
        for mutex_opt in self.not_required_if:
            if mutex_opt in opts:
                if current_opt:
                    raise click.UsageError("Illegal usage: '" + str(self.name) + "' is mutually exclusive with " + str(mutex_opt) + ".")
                else:
                    self.prompt = None
        return super(Mutex, self).handle_parse_result(ctx, opts, args)


class AstrosourceException(Exception):
    ''' Used to halt code with message '''
    pass


def cleanup(parentPath):
    folders = ['calibcats', 'periods', 'checkplots', 'eelbs', 'outputcats','outputplots','trimcats']
    for fd in folders:
        if (parentPath / fd).exists():
            shutil.rmtree(parentPath / fd)

    files = ['calibCompsUsed.csv', 'calibStands.csv', 'compsUsed.csv','screenedComps.csv', \
     'starVariability.csv', 'stdComps.csv', 'usedImages.txt', 'LightcurveStats.txt', \
     'periodEstimates.txt','calibrationErrors.txt']

    for fname in files:
        if (parentPath / fname).exists():
            (parentPath / fname).unlink()
    return

def folder_setup(parentPath=None):
    #create directory structure for output files
    if not parentPath:
        # Set default inputs directory to be relative to local path
        parentPath = Path(os.getcwd())
    paths = {
        'parent'     : parentPath,
        'outputPath' : parentPath / "outputplots",
        'outcatPath' : parentPath / "outputcats",
        'checkPath'  : parentPath / "checkplots",
        'inputs'     : parentPath / "inputs"
    }
    for k, path in paths.items():
        if not path.exists():
            os.makedirs(path)

    return paths

def photometry_files_to_array(parentPath):
    # Load in list of used files
    fileList=[]
    with open(parentPath / "usedImages.txt", "r") as f:
      for line in f:
        fileList.append(line.strip())

    # LOAD Phot FILES INTO LIST
    photFileArray=[]
    for file in fileList:
        loadPhot=np.genfromtxt(file, dtype=float, delimiter=',')
        if loadPhot.shape[1] > 6:
            loadPhot=np.delete(loadPhot,6,1)
            loadPhot=np.delete(loadPhot,6,1)
        photFileArray.append(loadPhot)
    photFileArray=np.asarray(photFileArray)

    return photFileArray, fileList

def get_targets(targetfile):
    targets = np.genfromtxt(targetfile, dtype=float, delimiter=',')
    # Remove any nan rows from targets
    targetRejecter=[]
    if not (targets.shape[0] == 4 and targets.size ==4):
        for z in range(targets.shape[0]):
          if np.isnan(targets[z][0]):
            targetRejecter.append(z)
        targets=np.delete(targets, targetRejecter, axis=0)
    return targets
