import numpy as np
from astropy import units as u
from astropy import wcs
from astropy.coordinates import SkyCoord
from astropy.io import fits
import glob
import sys
import os
import logging

from astrosource.utils import AstrosourceException

logger = logging.getLogger(__name__)

def rename_data_file(prihdr):

    prihdrkeys = prihdr.keys()

    if any("OBJECT" in s for s in prihdrkeys):
        objectTemp=prihdr['OBJECT'].replace('-','d').replace('+','p').replace('.','d').replace(' ','').replace('_','').replace('=','e').replace('(','').replace(')','').replace('<','').replace('>','').replace('/','')
    else:
        objectTemp="UNKNOWN"

    if 'FILTER' in prihdr:
        filterOne=(prihdr['FILTER'])
    else:
        filters = []
        filters.append(prihdr['FILTER1'])
        filters.append(prihdr['FILTER2'])
        filters.append(prihdr['FILTER3'])
        filter =list(set(filters))
        filter.remove('air')
        filterOne = filter[0]

    expTime=(str(prihdr['EXPTIME']).replace('.','d'))
    dateObs=(prihdr['DATE'].replace('-','d').replace(':','d').replace('.','d'))
    airMass=(str(prihdr['AIRMASS']).replace('.','a'))
    instruMe=(prihdr['INSTRUME']).replace(' ','').replace('/','').replace('-','')

    if (prihdr['MJD-OBS'] == 'UNKNOWN'):
        mjdObs = 'UNKNOWN'
    else:
        mjdObs = '{0:.10f}'.format(prihdr['MJD-OBS']).replace('.','d')
    newName="{}_{}_{}_{}_{}_{}_{}.csv".format(objectTemp, filterOne, expTime, dateObs, airMass,mjdObs, instruMe)

    return newName

def export_photometry_files(filelist, indir, filetype='csv'):
    phot_list = []
    for f in filelist:
        out = extract_photometry(f, indir)
        phot_list.append(out)
    return phot_list

def extract_photometry(infile, parentPath, outfile=None):

    hdulist = fits.open(infile)

    if not outfile:
        outfile = rename_data_file(hdulist[1].header)
    outfile = parentPath / outfile
    w = wcs.WCS(hdulist[1].header)
    data = hdulist[2].data
    xpixel = data['x']
    ypixel = data['y']
    ra, dec = w.wcs_pix2world(xpixel, ypixel, 1)
    counts = data['flux']
    countserr = data['fluxerr']
    np.savetxt(outfile, np.transpose([ra, dec, xpixel, ypixel, counts, countserr]), delimiter=',')
    return outfile

def gather_files(paths, filetype="fz"):
    # Get list of files

    filelist = paths['parent'].glob("*.{}".format(filetype))
    if filetype not in ['fits','fit','fz']:
        # Assume we are not dealing with image files but photometry files
        phot_list = [f for f in filelist]
    else:
        phot_list = export_photometry_files(filelist, paths['parent'])
    if not phot_list:
        raise AstrosourceException("No files of type '.{}' found in {}".format(filetype, paths['parent']))

    filters = set([os.path.basename(f).split('_')[1] for f in phot_list])

    logger.debug("Filter Set: {}".format(filters))
    if len(filters) > 1:
        raise AstrosourceException("Check your images, the script detected multiple filters in your file list. Astrosource currently only does one filter at a time.")
    return phot_list, list(filters)[0]

def find_stars(targetStars, paths, fileList, acceptDistance=1.0, minimumCounts=10000, maximumCounts=1000000, imageFracReject=0.0, starFracReject=0.1, rejectStart=7, minCompStars=1):
    """
    Finds stars useful for photometry in each photometry/data file

    Parameters
    ----------
    targetStars : list
            List of target tuples in the format (ra, dec, 0, 0). ra and dec must be in decimal
    indir : str
            Path to files
    filelist : str
            List of photometry files to try
    acceptDistance : float
            Furtherest distance in arcseconds for matches
    minimumCounts : int
            look for comparisons brighter than this
    maximumCounts : int
            look for comparisons dimmer than this
    imageFracReject: float
            This is a value which will reject images based on number of stars detected
    starFracReject : float
            This ia a value which will reject images that reject this fraction of available stars after....
    rejectStart : int
            This many initial images (lots of stars are expected to be rejected in the early images)
    minCompStars : int
            This is the minimum number of comp stars required

    Returns
    -------
    used_file : str
            Path to newly created file containing all images which are usable for photometry
    """

    #Initialisation values
    usedImages=[]
    # Generate a blank targetstars.csv file
    targetfile = paths['parent'] / "targetstars.csv"
    np.savetxt(targetfile, targetStars, delimiter=",", fmt='%0.8f')

    # LOOK FOR REJECTING NON-WCS IMAGES
    # If the WCS matching has failed, this function will remove the image from the list
    #wcsReject=[]
    #q=0
    fileSizer=0
    logger.info("Finding image with most stars detected and reject ones with bad WCS")
    referenceFrame = None

    for file in fileList:
        photFile = np.genfromtxt(file, dtype=float, delimiter=',')
        if (( np.asarray(photFile[:,0]) > 360).sum() > 0) :
            logger.debug("REJECT")
            logger.debug(file)
            fileList.remove(file)
        elif (( np.asarray(photFile[:,1]) > 90).sum() > 0) :
            logger.debug("REJECT")
            logger.debug(file)
            fileList.remove(file)
        else:
            # Sort through and find the largest file and use that as the reference file
            if photFile.size > fileSizer:
                phottmparr = np.asarray(photFile)
                if (( phottmparr[:,0] > 360).sum() == 0) and ( phottmparr[0][0] != 'null') and ( phottmparr[0][0] != 0.0) :
                    referenceFrame = photFile
                    fileSizer = photFile.size
                    logger.debug("{} - {}".format(photFile.size, file))
    if not referenceFrame.size:
        raise AstrosourceException("No suitable reference files found")

    logger.debug("Setting up reference Frame")
    fileRaDec = SkyCoord(ra=referenceFrame[:,0]*u.degree, dec=referenceFrame[:,1]*u.degree)

    logger.debug("Removing stars with low or high counts")
    rejectStars=[]
    # Check star has adequate counts
    for j in range(referenceFrame.shape[0]):
        if ( referenceFrame[j][4] < minimumCounts or referenceFrame[j][4] > maximumCounts ):
            rejectStars.append(int(j))
    logger.debug("Number of stars prior")
    logger.debug(referenceFrame.shape[0])

    referenceFrame=np.delete(referenceFrame, rejectStars, axis=0)

    logger.debug("Number of stars post")
    logger.debug(referenceFrame.shape[0])

    imgsize=imageFracReject * fileSizer # set threshold size
    rejStartCounter = 0
    imgReject = 0 # Number of images rejected due to high rejection rate
    loFileReject = 0 # Number of images rejected due to too few stars in the photometry file
    wcsFileReject=0
    for file in fileList:
        rejStartCounter = rejStartCounter +1
        photFile = np.genfromtxt(file, dtype=float, delimiter=',')
        # DUP fileRaDec = SkyCoord(ra=photFile[:,0]*u.degree, dec=photFile[:,1]*u.degree)

        logger.debug('Image Number: ' + str(rejStartCounter))
        logger.debug(file)
        logger.debug("Image threshold size: "+str(imgsize))
        logger.debug("Image catalogue size: "+str(photFile.size))
        if photFile.size > imgsize and photFile.size > 7:
            phottmparr = np.asarray(photFile)
            if (( phottmparr[:,0] > 360).sum() == 0) and ( phottmparr[0][0] != 'null') and ( phottmparr[0][0] != 0.0) :

                # Checking existance of stars in all photometry files
                rejectStars=[] # A list to hold what stars are to be rejected

                # Find whether star in reference list is in this phot file, if not, reject star.
                for j in range(referenceFrame.shape[0]):
                    photRAandDec = SkyCoord(ra = photFile[:,0]*u.degree, dec = photFile[:,1]*u.degree)
                    testStar = SkyCoord(ra = referenceFrame[j][0]*u.degree, dec = referenceFrame[j][1]*u.degree)
                    # This is the only line in the whole package which requires scipy
                    idx, d2d, d3d = testStar.match_to_catalog_sky(photRAandDec)
                    if (d2d.arcsecond > acceptDistance):
                        #"No Match! Nothing within range."
                        rejectStars.append(int(j))


            # if the rejectstar list is not empty, remove the stars from the reference List
            if rejectStars != []:

                if not (((len(rejectStars) / referenceFrame.shape[0]) > starFracReject) and rejStartCounter > rejectStart):
                    referenceFrame = np.delete(referenceFrame, rejectStars, axis=0)
                    logger.debug('**********************')
                    logger.debug('Stars Removed  : ' +str(len(rejectStars)))
                    logger.debug('Remaining Stars: ' +str(referenceFrame.shape[0]))
                    logger.debug('**********************')
                    usedImages.append(file)
                else:
                    logger.debug('**********************')
                    logger.debug('Image Rejected due to too high a fraction of rejected stars')
                    logger.debug(len(rejectStars) / referenceFrame.shape[0])
                    logger.debug('**********************')
                    imgReject=imgReject+1
            else:
                logger.debug('**********************')
                logger.debug('All Stars Present')
                logger.debug('**********************')
                usedImages.append(file)

            # If we have removed all stars, we have failed!
            if (referenceFrame.shape[0]==0):
                logger.error("Problem file - {}".format(file))
                raise AstrosourceException("All Stars Removed. Try removing problematic files or raising the imageFracReject")

            if (referenceFrame.shape[0]< minCompStars):
                logger.error("Problem file - {}".format(file))
                raise AstrosourceException("There are fewer than the requested number of Comp Stars. Try removing problematic files or raising the imageFracReject")

        elif photFile.size < 7:
            logger.error('**********************')
            logger.error("WCS Coordinates broken")
            logger.error('**********************')
            wcsFileReject=wcsFileReject+1
        else:
            logger.error('**********************')
            logger.error("CONTAINS TOO FEW STARS")
            logger.error('**********************')
            loFileReject=loFileReject+1

    # Construct the output file containing candidate comparison stars
    outputComps=[]
    for j in range (referenceFrame.shape[0]):
        outputComps.append([referenceFrame[j][0],referenceFrame[j][1]])

    logger.debug("These are the identified common stars of sufficient brightness that are in every image")
    logger.debug(outputComps)

    logger.info('Images Rejected due to high star rejection rate: {}'.format(imgReject))
    logger.info('Images Rejected due to low file size: {}'.format(loFileReject))
    logger.info('Out of this many original images: {}'.format(len(fileList)))

    logger.info("Number of candidate Comparison Stars Detected: " + str(len(outputComps)))
    logger.info('Output sent to screenedComps.csv ready for use in Comparison')

    screened_file = paths['parent'] / "screenedComps.csv"
    np.savetxt(screened_file, outputComps, delimiter=",", fmt='%0.8f')
    used_file = paths['parent'] / "usedImages.txt"
    with open(used_file, "w") as f:
        for s in usedImages:
            f.write(str(s) +"\n")

    return usedImages
