import glob
import sys
import os
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astroquery.vo_conesearch import conesearch
from astroquery.vo_conesearch import ConeSearch
from astroquery.vizier import Vizier


from astrosource.utils import AstrosourceException

import logging

logger = logging.getLogger(__name__)


def find_comparisons(parentPath=None, stdMultiplier=3, thresholdCounts=1000000000, variabilityMultiplier=2.5, removeTargets=1, acceptDistance=5.0):
    '''
    Find stable comparison stars for the target photometry

    Parameters
    ----------
    parentPath : str or Path object
            Path to the data files
    stdMultiplier : int
            Number of standard deviations above the mean to cut off the top. The cycle will continue until there are no stars this many std.dev above the mean
    thresholdCounts : int
            Target countrate for the ensemble comparison. The lowest variability stars will be added until this countrate is reached.
    variabilityMax : float
            This will stop adding ensemble comparisons if it starts using stars higher than this variability
    removeTargets : int
            Set this to 1 to remove targets from consideration for comparison stars
    acceptDistance : float
            Furthest distance in arcseconds for matches

    Returns
    -------
    outfile : str

    '''

    # Get list of phot files
    if not parentPath:
        parentPath = Path(os.getcwd())
    if type(parentPath) == 'str':
        parentPath = Path(parentPath)

    compFile, photFileArray, fileList = read_data_files(parentPath)

    if removeTargets == 1:
        targetFile = remove_targets(parentPath, compFile, acceptDistance)

    while True:
        # First half of Loop: Add up all of the counts of all of the comparison stars
        # To create a gigantic comparison star.

        logger.debug("Please wait... calculating ensemble comparison star for each image")
        fileCount = ensemble_comparisons(photFileArray, compFile)

        # Second half of Loop: Calculate the variation in each candidate comparison star in brightness
        # compared to this gigantic comparison star.
        rejectStar=[]
        stdCompStar, sortStars = calculate_comparison_variation(compFile, photFileArray, fileCount)
        variabilityMax=(np.min(stdCompStar)*variabilityMultiplier)

        # Calculate and present the sample statistics
        stdCompMed=np.median(stdCompStar)
        stdCompStd=np.std(stdCompStar)

        logger.debug(fileCount)
        logger.debug(stdCompStar)
        logger.debug(np.median(stdCompStar))
        logger.debug(np.std(stdCompStar))

        # Delete comparisons that have too high a variability
        starRejecter=[]
        for j in range(len(stdCompStar)):
            logger.debug(stdCompStar[j])
            if ( stdCompStar[j] > (stdCompMed + (stdMultiplier*stdCompStd)) ):
                logger.debug("Star Rejected, Variability too high!")
                starRejecter.append(j)

            if ( np.isnan(stdCompStar[j]) ) :
                logger.debug("Star Rejected, Invalid Entry!")
                starRejecter.append(j)
        if starRejecter:
            logger.warning("Rejected {} stars".format(len(starRejecter)))


        compFile = np.delete(compFile, starRejecter, axis=0)
        sortStars = np.delete(sortStars, starRejecter, axis=0)

        # Calculate and present statistics of sample of candidate comparison stars.
        logger.info("Median variability {:.6f}".format(np.median(stdCompStar)))
        logger.info("Std variability {:.6f}".format(np.std(stdCompStar)))
        logger.info("Min variability {:.6f}".format(np.min(stdCompStar)))
        logger.info("Max variability {:.6f}".format(np.max(stdCompStar)))
        logger.info("Number of Stable Comparison Candidates {}".format(compFile.shape[0]))
        # Once we have stopped rejecting stars, this is our final candidate catalogue then we start to select the subset of this final catalogue that we actually use.
        if (starRejecter == []):
            break
        else:
            logger.warning("Trying again")

    logger.info('Statistical stability reached.')
    outfile, num_comparisons = final_candidate_catalogue(parentPath, photFileArray, sortStars, thresholdCounts, variabilityMax)
    return outfile, num_comparisons

def final_candidate_catalogue(parentPath, photFileArray, sortStars, thresholdCounts, variabilityMax):

    logger.info('List of stable comparison candidates output to stdComps.csv')

    np.savetxt(parentPath / "stdComps.csv", sortStars, delimiter=",", fmt='%0.8f')

    # The following process selects the subset of the candidates that we will use (the least variable comparisons that hopefully get the request countrate)

    # Sort through and find the largest file and use that as the reference file
    referenceFrame, fileRaDec = find_reference_frame(photFileArray)

    # SORT THE COMP CANDIDATE FILE such that least variable comparison is first
    sortStars=(sortStars[sortStars[:,2].argsort()])

    # PICK COMPS UNTIL OVER THE THRESHOLD OF COUNTS OR VRAIABILITY ACCORDING TO REFERENCE IMAGE
    logger.debug("PICK COMPARISONS UNTIL OVER THE THRESHOLD ACCORDING TO REFERENCE IMAGE")
    compFile=[]
    tempCountCounter=0.0
    finalCountCounter=0.0
    for j in range(sortStars.shape[0]):
        matchCoord=SkyCoord(ra=sortStars[j][0]*u.degree, dec=sortStars[j][1]*u.degree)
        idx, d2d, d3d = matchCoord.match_to_catalog_sky(fileRaDec)
        tempCountCounter=np.add(tempCountCounter,referenceFrame[idx][4])

        if tempCountCounter < thresholdCounts:
            if sortStars[j][2] < variabilityMax:
                compFile.append([sortStars[j][0],sortStars[j][1],sortStars[j][2]])
                logger.debug("Comp " + str(j+1) + " std: " + str(sortStars[j][2]))
                logger.debug("Cumulative Counts thus far: " + str(tempCountCounter))
                finalCountCounter=np.add(finalCountCounter,referenceFrame[idx][4])

    logger.debug("Selected stars listed below:")
    logger.debug(compFile)

    logger.info("Finale Ensemble Counts: " + str(finalCountCounter))
    compFile=np.asarray(compFile)

    logger.info(str(compFile.shape[0]) + " Stable Comparison Candidates below variability threshold output to compsUsed.csv")
    #logger.info(compFile.shape[0])

    outfile = parentPath / "compsUsed.csv"
    np.savetxt(outfile, compFile, delimiter=",", fmt='%0.8f')

    return outfile, compFile.shape[0]

def find_reference_frame(photFileArray):
    fileSizer = 0
    logger.info("Finding image with most stars detected")
    for photFile in photFileArray:
        if photFile.size > fileSizer:
            referenceFrame = photFile
            logger.debug(photFile.size)
            fileSizer = photFile.size
    logger.info("Setting up reference Frame")
    fileRaDec = SkyCoord(ra=referenceFrame[:,0]*u.degree, dec=referenceFrame[:,1]*u.degree)
    return referenceFrame, fileRaDec

def read_data_files(parentPath):
    fileList=[]
    for line in (parentPath / "usedImages.txt").read_text().strip().split('\n'):
        fileList.append(line.strip())

    # LOAD Phot FILES INTO LIST

    photFileArray = []
    for file in fileList:
        photFileArray.append(np.genfromtxt(file, dtype=float, delimiter=','))
    photFileArray = np.asarray(photFileArray)


    #Grab the candidate comparison stars
    screened_file = parentPath / "screenedComps.csv"
    compFile = np.genfromtxt(screened_file, dtype=float, delimiter=',')
    return compFile, photFileArray, fileList

def ensemble_comparisons(photFileArray, compFile):
    fileCount=[]
    for photFile in photFileArray:
        allCounts=0.0
        fileRaDec = SkyCoord(ra=photFile[:,0]*u.degree, dec=photFile[:,1]*u.degree)
        for cf in compFile:
            matchCoord = SkyCoord(ra=cf[0]*u.degree, dec=cf[1]*u.degree)
            idx, d2d, d3d = matchCoord.match_to_catalog_sky(fileRaDec)
            allCounts = np.add(allCounts,photFile[idx][4])


        logger.debug("Total Counts in Image: {:.2f}".format(allCounts))
        fileCount=np.append(fileCount, allCounts)
    return fileCount

def calculate_comparison_variation(compFile, photFileArray, fileCount):
    stdCompStar=[]
    sortStars=[]

    for cf in compFile:
        compDiffMags = []
        q=0
        logger.debug("*************************")
        logger.debug("RA : " + str(cf[0]))
        logger.debug("DEC: " + str(cf[1]))
        for imgs in range(photFileArray.shape[0]):
            photFile = photFileArray[imgs]
            fileRaDec = SkyCoord(ra=photFile[:,0]*u.degree, dec=photFile[:,1]*u.degree)
            matchCoord = SkyCoord(ra=cf[0]*u.degree, dec=cf[1]*u.degree)
            idx, d2d, d3d = matchCoord.match_to_catalog_sky(fileRaDec)
            compDiffMags = np.append(compDiffMags,2.5 * np.log10(photFile[idx][4]/fileCount[q]))
            q = np.add(q,1)

        logger.debug("VAR: " +str(np.std(compDiffMags)))
        stdCompStar.append(np.std(compDiffMags))
        sortStars.append([cf[0],cf[1],np.std(compDiffMags),0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0])
    return stdCompStar, sortStars

def remove_targets(parentPath, compFile, acceptDistance):
    max_sep=acceptDistance * u.arcsec
    logger.info("Removing Target Stars from potential Comparisons")
    targetFile = np.genfromtxt(parentPath / 'targetstars.csv', dtype=float, delimiter=',')
    fileRaDec = SkyCoord(ra=compFile[:,0]*u.degree, dec=compFile[:,1]*u.degree)
    # Remove any nan rows from targetFile
    targetRejecter=[]
    if not (targetFile.shape[0] == 4 and targetFile.size ==4):
        for z in range(targetFile.shape[0]):
          if np.isnan(targetFile[z][0]):
            targetRejecter.append(z)
        targetFile=np.delete(targetFile, targetRejecter, axis=0)

    # Remove targets from consideration
    if len(targetFile)== 4:
        loopLength=1
    else:
        loopLength=targetFile.shape[0]
    targetRejects=[]
    tg_file_len = len(targetFile)
    for tf in targetFile:
        if tg_file_len == 4:
            varCoord = SkyCoord(targetFile[0],(targetFile[1]), frame='icrs', unit=u.deg)
        else:
            varCoord = SkyCoord(tf[0],(tf[1]), frame='icrs', unit=u.deg) # Need to remove target stars from consideration
        idx, d2d, _ = varCoord.match_to_catalog_sky(fileRaDec)
        if d2d.arcsecond < acceptDistance:
            targetRejects.append(idx)
        if tg_file_len == 4:
            break
    compFile=np.delete(compFile, idx, axis=0)

    # Get Average RA and Dec from file
    if compFile.shape[0] == 13:
        logger.debug(compFile[0])
        logger.debug(compFile[1])
        avgCoord=SkyCoord(ra=(compFile[0])*u.degree, dec=(compFile[1]*u.degree))

    else:
        logger.debug(np.average(compFile[:,0]))
        logger.debug(np.average(compFile[:,1]))
        avgCoord=SkyCoord(ra=(np.average(compFile[:,0]))*u.degree, dec=(np.average(compFile[:,1]))*u.degree)


    # Check VSX for any known variable stars and remove them from the list
    variableResult=Vizier.query_region(avgCoord, '0.33 deg', catalog='VSX')['B/vsx/vsx']

    logger.debug(variableResult)

    variableResult=variableResult.to_pandas()

    logger.debug(variableResult.keys())

    variableSearchResult=variableResult[['RAJ2000','DEJ2000']].to_numpy()


    raCat=variableSearchResult[:,0]
    logger.debug(raCat)
    decCat=variableSearchResult[:,1]
    logger.debug(decCat)

    varStarReject=[]
    for t in range(raCat.size):
      logger.debug(raCat[t])
      compCoord=SkyCoord(ra=raCat[t]*u.degree, dec=decCat[t]*u.degree)
      logger.debug(compCoord)
      catCoords=SkyCoord(ra=compFile[:,0]*u.degree, dec=compFile[:,1]*u.degree)
      idxcomp,d2dcomp,d3dcomp=compCoord.match_to_catalog_sky(catCoords)
      logger.debug(d2dcomp)
      if d2dcomp *u.arcsecond < max_sep*u.arcsecond:
        logger.debug("match!")
        varStarReject.append(t)
      else:
        logger.debug("no match!")


    logger.debug("Number of stars prior to VSX reject")
    logger.debug(compFile.shape[0])
    compFile=np.delete(compFile, varStarReject, axis=0)
    logger.debug("Number of stars post to VSX reject")
    logger.debug(compFile.shape[0])


    if (compFile.shape[0] ==1):
        compFile=[[compFile[0][0],compFile[0][1],0.01]]
        compFile=np.asarray(compFile)
        np.savetxt(parentPath / "compsUsed.csv", compFile, delimiter=",", fmt='%0.8f')
        sortStars=[[compFile[0][0],compFile[0][1],0.01,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]]
        sortStars=np.asarray(sortStars)
        np.savetxt("stdComps.csv", sortStars, delimiter=",", fmt='%0.8f')
        raise AstrosourceException("Looks like you have a single comparison star!")
    return compFile

def find_comparisons_calibrated(filterCode, paths=None, max_magerr=0.05, stdMultiplier=2, variabilityMultiplier=2, panStarrsInstead=False):

    parentPath = paths['parent']
    calibPath = parentPath / "calibcats"
    if not calibPath.exists():
        os.makedirs(calibPath)

    Vizier.ROW_LIMIT = -1
    max_sep=1.0 * u.arcsec

    # Get List of Files Used
    fileList=[]
    for line in (parentPath / "usedImages.txt").read_text().strip().split('\n'):
        fileList.append(line.strip())

    logger.debug("Filter Set: " + filterCode)

    # Load compsused
    compFile = np.genfromtxt(parentPath / 'stdComps.csv', dtype=float, delimiter=',')
    logger.debug(compFile.shape[0])

    if compFile.shape[0] == 13:
        compCoords=SkyCoord(ra=compFile[0]*u.degree, dec=compFile[1]*u.degree)
    else:
        compCoords=SkyCoord(ra=compFile[:,0]*u.degree, dec=compFile[:,1]*u.degree)

    # Get Average RA and Dec from file
    if compFile.shape[0] == 13:
        logger.debug(compFile[0])
        logger.debug(compFile[1])
        avgCoord=SkyCoord(ra=(compFile[0])*u.degree, dec=(compFile[1]*u.degree))

    else:
        logger.debug(np.average(compFile[:,0]))
        logger.debug(np.average(compFile[:,1]))
        avgCoord=SkyCoord(ra=(np.average(compFile[:,0]))*u.degree, dec=(np.average(compFile[:,1]))*u.degree)

    # get results from internetz

    if filterCode=='B' or filterCode=='V':
        #collect APASS results
        apassResult=Vizier.query_region(avgCoord, '0.33 deg', catalog='APASS')['II/336/apass9']

        logger.debug(apassResult)
        apassResult=apassResult.to_pandas()

        logger.debug(apassResult.keys())

        apassSearchResult=apassResult[['RAJ2000','DEJ2000','Bmag','e_Bmag','Vmag','e_Vmag']].as_matrix()

        logger.debug(apassSearchResult)

        raCat=apassSearchResult[:,0]
        logger.debug(raCat)
        decCat=apassSearchResult[:,1]
        logger.debug(decCat)
        if filterCode=='B':
            magCat=apassSearchResult[:,2]
            logger.debug(magCat)
            emagCat=apassSearchResult[:,3]
            logger.debug(emagCat)

        if filterCode=='V':
            magCat=apassSearchResult[:,4]
            logger.debug(magCat)
            emagCat=apassSearchResult[:,5]
            logger.debug(emagCat)


    elif filterCode=='up' or filterCode=='gp' or filterCode=='rp' or filterCode=='ip' or filterCode=='zs':
        # Are there entries in SDSS?
        sdssResult=SDSS.query_region(avgCoord, '0.33 deg')
        #print(sdssResult)
        sdssFind=1

        # If not in SDSS, try Skymapper
        if sdssResult==None:
            sdssFind=0
            logger.debug("Not found in SDSS, must be in the South.")
            #logger.debug(ConeSearch.URL)
            ConeSearch.URL='http://skymapper.anu.edu.au/sm-cone/aus/query?'
            sdssResult=ConeSearch.query_region(avgCoord, '0.33 deg')

            logger.debug(sdssResult)

            searchResult=sdssResult.to_table().to_pandas()

            logger.debug(searchResult)

            sdssSearchResult=searchResult[['raj2000','dej2000','u_psf','e_u_psf','g_psf','e_g_psf','r_psf','e_r_psf','i_psf','e_i_psf','z_psf','e_z_psf']].as_matrix()

            logger.debug(sdssSearchResult[:,0])

            raCat=sdssSearchResult[:,0]
            logger.debug(raCat)
            decCat=sdssSearchResult[:,1]
            logger.debug(decCat)
            if filterCode=='up':
                magCat=sdssSearchResult[:,2]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,3]
                logger.debug(emagCat)
            if filterCode=='gp':
                magCat=sdssSearchResult[:,4]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,5]
                logger.debug(emagCat)
            if filterCode=='rp':
                magCat=sdssSearchResult[:,6]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,7]
                logger.debug(emagCat)
            if filterCode=='ip':
                magCat=sdssSearchResult[:,8]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,9]
                logger.debug(emagCat)
            if filterCode=='zs':
                magCat=sdssSearchResult[:,10]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,11]
                logger.debug(emagCat)

        elif panStarrsInstead and filterCode!='up':
            logger.debug("Panstarrs!")

            sdssResult=Vizier.query_region(avgCoord, '0.33 deg', catalog='PanStarrs')['II/349/ps1']
            logger.debug(sdssResult)
            logger.debug(sdssResult.keys())


            searchResult=sdssResult.to_pandas()

            logger.debug(searchResult)

            sdssSearchResult=searchResult[['RAJ2000','DEJ2000','gmag','e_gmag','gmag','e_gmag','rmag','e_rmag','imag','e_imag','zmag','e_zmag']].as_matrix()

            logger.debug(sdssSearchResult[:,0])

            raCat=sdssSearchResult[:,0]
            logger.debug(raCat)
            decCat=sdssSearchResult[:,1]
            logger.debug(decCat)
            if filterCode=='up':
                magCat=sdssSearchResult[:,2]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,3]
                logger.debug(emagCat)
            if filterCode=='gp':
                magCat=sdssSearchResult[:,4]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,5]
                logger.debug(emagCat)
            if filterCode=='rp':
                magCat=sdssSearchResult[:,6]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,7]
                logger.debug(emagCat)
            if filterCode=='ip':
                magCat=sdssSearchResult[:,8]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,9]
                logger.debug(emagCat)
            if filterCode=='zs':
                magCat=sdssSearchResult[:,10]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,11]
                logger.debug(emagCat)


        else:
            logger.debug("goodo lets do the sdss stuff then.")
            sdssResult=Vizier.query_region(avgCoord, '0.33 deg', catalog='SDSS')['V/147/sdss12']
            logger.debug(sdssResult)
            logger.debug(sdssResult.keys())

            searchResult=sdssResult.to_pandas()

            logger.debug(searchResult)

            sdssSearchResult=searchResult[['RA_ICRS','DE_ICRS','umag','e_umag','gmag','e_gmag','rmag','e_rmag','imag','e_imag','zmag','e_zmag']].as_matrix()

            logger.debug(sdssSearchResult[:,0])

            raCat=sdssSearchResult[:,0]
            logger.debug(raCat)
            decCat=sdssSearchResult[:,1]
            logger.debug(decCat)
            if filterCode=='up':
                magCat=sdssSearchResult[:,2]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,3]
                logger.debug(emagCat)
            if filterCode=='gp':
                magCat=sdssSearchResult[:,4]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,5]
                logger.debug(emagCat)
            if filterCode=='rp':
                magCat=sdssSearchResult[:,6]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,7]
                logger.debug(emagCat)
            if filterCode=='ip':
                magCat=sdssSearchResult[:,8]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,9]
                logger.debug(emagCat)
            if filterCode=='zs':
                magCat=sdssSearchResult[:,10]
                logger.debug(magCat)
                emagCat=sdssSearchResult[:,11]
                logger.debug(emagCat)

    #Setup standard catalogue coordinates
    catCoords=SkyCoord(ra=raCat*u.degree, dec=decCat*u.degree)


    #Get calib mags for least variable IDENTIFIED stars.... not the actual stars in compUsed!! Brighter, less variable stars may be too bright for calibration!
    #So the stars that will be used to calibrate the frames to get the OTHER stars.
    calibStands=[]
    if compFile.shape[0] ==13:
        lenloop=1
    else:
        lenloop=len(compFile[:,0])
    for q in range(lenloop):
        if compFile.shape[0] ==13:
            compCoord=SkyCoord(ra=compFile[0]*u.degree, dec=compFile[1]*u.degree)
        else:
            compCoord=SkyCoord(ra=compFile[q][0]*u.degree, dec=compFile[q][1]*u.degree)
        idxcomp,d2dcomp,d3dcomp=compCoord.match_to_catalog_sky(catCoords)

        if d2dcomp *u.arcsecond < max_sep*u.arcsecond:
            if not np.isnan(magCat[idxcomp]):
                #logger.debug(idxcomp)
                #logger.debug(d2dcomp)
                #logger.debug(magCat[idxcomp])
                #logger.debug(emagCat[idxcomp])

                if compFile.shape[0] ==13:
                    calibStands.append([compFile[0],compFile[1],compFile[2],magCat[idxcomp],emagCat[idxcomp]])
                else:
                    calibStands.append([compFile[q][0],compFile[q][1],compFile[q][2],magCat[idxcomp],emagCat[idxcomp]])

    # Get the set of least variable stars to use as a comparison to calibrate the files (to eventually get the *ACTUAL* standards
    #logger.debug(np.asarray(calibStands).shape[0])
    if np.asarray(calibStands).shape[0] == 0:
        logger.info("We could not find a suitable match between any of your stars and the calibration catalogue")
        logger.info("You might need to reduce the low value (usually 10000) to get some dimmer stars in script 1")
        raise AstrosourceException("Perhaps try 5000 then 1000. You are trying to find dim stars to calibrate to.")

    varimin=(np.min(np.asarray(calibStands)[:,2])) * variabilityMultiplier

    logger.debug("varimin")
    #logger.debug(np.asarray(calibStands)[:,2])
    logger.debug(varimin)

    calibStandsReject=[]
    for q in range(len(np.asarray(calibStands)[:,0])):
        if calibStands[q][2] > varimin:
            calibStandsReject.append(q)
            #logger.debug(calibStands[q][2])

    calibStands=np.delete(calibStands, calibStandsReject, axis=0)

    calibStand=np.asarray(calibStands)

    np.savetxt(parentPath / "calibStands.csv", calibStands , delimiter=",", fmt='%0.8f')
    # Lets use this set to calibrate each datafile and pull out the calibrated compsused magnitudes
    compUsedFile = np.genfromtxt(parentPath / 'compsUsed.csv', dtype=float, delimiter=',')

    calibCompUsed=[]

    logger.debug("CALIBRATING EACH FILE")
    for file in fileList:

        logger.debug(file)

        #Get the phot file into memory
        photFile = np.genfromtxt(parentPath / file, dtype=float, delimiter=',')
        photCoords=SkyCoord(ra=photFile[:,0]*u.degree, dec=photFile[:,1]*u.degree)

        #Convert the phot file into instrumental magnitudes
        for r in range(len(photFile[:,0])):
            photFile[r,5]=1.0857 * (photFile[r,5]/photFile[r,4])
            photFile[r,4]=-2.5*np.log10(photFile[r,4])

        #Pull out the CalibStands out of each file
        tempDiff=[]
        for q in range(len(calibStands[:,0])):
            calibCoord=SkyCoord(ra=calibStand[q][0]*u.degree,dec=calibStand[q][1]*u.degree)
            idx,d2d,d3d=calibCoord.match_to_catalog_sky(photCoords)
            tempDiff.append(calibStand[q,3]-photFile[idx,4])

        #logger.debug(tempDiff)
        tempZP= (np.median(tempDiff))
        #logger.debug(np.std(tempDiff))

        #Shift the magnitudes in the phot file by the zeropoint
        for r in range(len(photFile[:,0])):
            photFile[r,4]=photFile[r,4]+tempZP

        file = Path(file)
        #Save the calibrated photfiles to the calib directory
        np.savetxt(calibPath / "{}.calibrated.{}".format(file.stem, file.suffix), photFile, delimiter=",", fmt='%0.8f')

        #Look within photfile for ACTUAL usedcomps.csv and pull them out
        lineCompUsed=[]
        if compUsedFile.shape[0] ==3 and compUsedFile.size == 3:
            lenloop=1
        else:
            lenloop=len(compUsedFile[:,0])

        #logger.debug(compUsedFile.size)
        for r in range(lenloop):
            if compUsedFile.shape[0] ==3 and compUsedFile.size ==3:
                compUsedCoord=SkyCoord(ra=compUsedFile[0]*u.degree,dec=compUsedFile[1]*u.degree)
            else:
                compUsedCoord=SkyCoord(ra=compUsedFile[r][0]*u.degree,dec=compUsedFile[r][1]*u.degree)
            idx,d2d,d3d=compUsedCoord.match_to_catalog_sky(photCoords)
            lineCompUsed.append(photFile[idx,4])

        #logger.debug(lineCompUsed)
        calibCompUsed.append(lineCompUsed)


    # Finalise calibcompsusedfile
    #logger.debug(calibCompUsed)

    calibCompUsed=np.asarray(calibCompUsed)
    #logger.debug(calibCompUsed[0,:])

    finalCompUsedFile=[]
    sumStd=[]
    for r in range(len(calibCompUsed[0,:])):
        #Calculate magnitude and stdev
        #logger.debug(calibCompUsed[:,r])
        #logger.debug(np.median(calibCompUsed[:,r]))
        #logger.debug(np.std(calibCompUsed[:,r]))
        #sumStd=sumStd+np.std(calibCompUsed[:,r])
        sumStd.append(np.std(calibCompUsed[:,r]))
        #logger.debug(calibCompUsed[:,r])
        #logger.debug(np.std(calibCompUsed[:,r]))
        if compUsedFile.shape[0] ==3  and compUsedFile.size ==3:
            finalCompUsedFile.append([compUsedFile[0],compUsedFile[1],compUsedFile[2],np.median(calibCompUsed[:,r]),np.asarray(calibStands[0])[4]])
        else:
            finalCompUsedFile.append([compUsedFile[r][0],compUsedFile[r][1],compUsedFile[r][2],np.median(calibCompUsed[:,r]),np.std(calibCompUsed[:,r])])

    #logger.debug(finalCompUsedFile)
    logger.debug(" ")
    sumStd=np.asarray(sumStd)

    errCalib = np.median(sumStd) / pow((len(calibCompUsed[0,:])), 0.5)

    #logger.debug(len(calibCompUsed[0,:]))
    if len(calibCompUsed[0,:]) == 1:
        logger.debug("As you only have one comparison, the uncertainty in the calibration is unclear")
        logger.debug("But we can take the catalogue value, although we should say this is a lower uncertainty")
        logger.debug("Error/Uncertainty in Calibration: " +str(np.asarray(calibStands[0])[4]))
    else:
        logger.debug("Median Standard Deviation of any one star: " + str(np.median(sumStd)))
        logger.debug("Standard Error/Uncertainty in Calibration: " +str(errCalib))

    with open(parentPath / "calibrationErrors.txt", "w") as f:
        f.write("Median Standard Deviation of any one star: " + str(np.median(sumStd)) +"\n")
        f.write("Standard Error/Uncertainty in Calibration: " +str(errCalib))

    #logger.debug(finalCompUsedFile)
    compFile = np.asarray(finalCompUsedFile)
    np.savetxt(parentPath / "calibCompsUsed.csv", compFile, delimiter=",", fmt='%0.8f')
    return compFile
