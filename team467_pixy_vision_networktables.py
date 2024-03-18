from __future__ import print_function

import sys

sys.path.append('/home/pi/pixy2/build/python_demos')

import pixy

from ctypes import *
import math
from datetime import datetime
from pixy import *

import time
from time import strftime
from networktables import NetworkTables
from networktables.util import ntproperty
import logging
#for logging values to networktables
# Pixy2 Python SWIG get blocks example #


print("Pixy2 Get Blocks Initialization")

pixy.init()
print("Pixy2 init done")

pixy.change_prog("color_connected_components");
print("Pixy2 connected components done")

#The following set of parameters summarize the overall location of the block detected (note) within the field of view.
class Blocks(Structure):
    _fields_ = [("m_signature", c_uint), 
                ("m_x", c_uint), 
                ("m_y", c_uint),
                ("m_width", c_uint), 
                ("m_height", c_uint),
                ("m_angle", c_uint),
                ("m_index", c_uint),
                ("m_age", c_uint)]


# pixy get blocks returns this data type
raw_blocks = BlockArray(10)

# pixy blocks copied to local data types for handling
local_raw_blocks = []


class pixy2FovIdealNoteSz():
    """ defines grid for field of view of pixy with ideal note sizes in different cells."""
    """ ideal note size (width , height) closest to pixy2, in middle, furthest"""

    def __init__(self, i_width, i_height):
        self.i_width = i_width
        self.i_height = i_height

######## BEGIN: adjustable parameters for filtering blocks ########
# setting for 3 ideal note sizes(width & height)
pixy2_i_note_sz = []

# this data is for camera at height 20 inches, mounted at an angle of 30 degrees vertically
# horizontal FoV is 60 degrees & veritical FoV is 40 degrees

# closest to pixy2 camera
pixy2_i_note_sz.append(pixy2FovIdealNoteSz(110, 50))
# in middle of Pixy2's FOV
pixy2_i_note_sz.append(pixy2FovIdealNoteSz(110, 50))
# furthest in Pixy2's FOV
pixy2_i_note_sz.append(pixy2FovIdealNoteSz(110, 50))

# detected note size % of ideal note size (reliable if within +- R %)
note_w_R_percent = 30.0  # 30 % on width
note_h_R_percent = 50.0  # 50 % on height  #not being used

# max allowed absolute angle of a block (degrees). Can be at most 30 degrees or -30 degrees.
max_angle_filter = 30

# pixy get block interval
get_blk_interval = (10 / 1000)  # sleep for 10 ms before calling pixy and detecting objects again


# to disable logging, see the log code section

######## END: adjustable parameters for filtering blocks ########


def note_get_pixy2_fov_cell(x, y):
    # if y (pixel coordinates) is furthest from camera, in middle, or closest
    if y >= 0 and y <= 70:
        return 2
    elif y >= 71 and y <= 140:
        return 1
    else:
        return 0

#Checks for complete block (whole note) match
def block_is_match_w_whole_note(x, y, width, height):
    is_whole_note = False
    is_note_too_big = False
    is_frag_note = False

    note_cell = note_get_pixy2_fov_cell(x, y)

    pixy2NtLog.debug('check BLOCK match: X=%3d Y=%3d WIDTH=%3d HEIGHT=%3d cell=%d]' % (x, y, width, height, note_cell))

    # check for ideal block match for note: check only width; height is very erratic so don't check
    if ((width > (pixy2_i_note_sz[note_cell].i_width * (1 - note_w_R_percent / 100))) and \
            (width < pixy2_i_note_sz[note_cell].i_width * (1 + note_w_R_percent / 100))):
        is_whole_note = True

    elif (width > pixy2_i_note_sz[note_cell].i_width * (1 + note_w_R_percent / 100)):
        pixy2NtLog.debug('block not matched')
        is_note_too_big = True

    else:
        is_frag_note = True

    return (is_whole_note, is_note_too_big, is_frag_note)


def block_coalesce_fragments(f_blk_count_arg, blk_frags_arg):
    #### ToDo calculate actual note_cell; for now using always 0
    note_cell = 0
    w_blk_count_from_frags = 0
    blocks_whole_from_frags = []

    max_frags = 0
    max_avg_x = 0
    max_avg_y = 0

    for i in range(0, f_blk_count_arg):
        num_frags = 0
        total_x = 0
        total_y = 0
        max_width = 0
        min_x = 316  # set to max x in camera fov (note the opposite)
        max_x = 0  # set to min x in camera fov (note the opposite)

        for j in range(0, f_blk_count_arg):
            if ((abs(blk_frags_arg[i].m_x - blk_frags_arg[j].m_x) < (
                    pixy2_i_note_sz[note_cell].i_width * (1 + note_w_R_percent / 100))) and \
                    (abs(blk_frags_arg[i].m_y - blk_frags_arg[j].m_y) < (
                            pixy2_i_note_sz[note_cell].i_height * (1 + note_h_R_percent / 100)))):
                pixy2NtLog.debug(
                    'possible coalesce Fragments[%d] & [%d]: [X=%3d Y=%3d W=%3d H=%3d] [X=%3d, Y=%3d, W=%3d, H=%3d]' % (
                    i, j, blk_frags_arg[i].m_x, blk_frags_arg[i].m_y, blk_frags_arg[i].m_width,
                    blk_frags_arg[i].m_height, blk_frags_arg[j].m_x, blk_frags_arg[j].m_y, blk_frags_arg[j].m_width,
                    blk_frags_arg[j].m_height))

                num_frags += 1
                total_x += blk_frags_arg[j].m_x
                total_y += blk_frags_arg[j].m_y
                if (max_width < blk_frags_arg[j].m_width):
                    max_width = blk_frags_arg[j].m_width
                if (min_x > blk_frags_arg[j].m_x):
                    min_x = blk_frags_arg[j].m_x
                if (max_x < blk_frags_arg[j].m_x):
                    max_x = blk_frags_arg[j].m_x

        note_w_min_thres = pixy2_i_note_sz[note_cell].i_width * (1.0 - note_w_R_percent / 100)
        if ((max_width < note_w_min_thres) and \
                ((max_x - min_x) < note_w_min_thres)):
            # reject this group of fragments
            pixy2NtLog.warning(
                '[Reject coalesced fragments: max_width [%d] & (max_x[%d]-min_x[%d]) less than note width threshold (%d)]' % (
                max_width, max_x, min_x, note_w_min_thres))
            continue

        elif num_frags > max_frags:
            pixy2NtLog.debug('[Tentative coalesced fragments: with block[i=%d] & conforming js]' % (i))
            max_frags = num_frags
            max_avg_x = total_x / num_frags
            max_avg_y = total_y / num_frags
            if (max_width > (max_x - min_x)):
                estimated_width = max_width
            else:
                estimated_width = max_x - min_x

    # add the max entry to whole detected block; at least 2 fragments should have been detected
    if (max_frags >= 2):
        blocks_whole_from_frags.append(Blocks(2, 0, 0, 0, 0, 0, 0, 123))
        blocks_whole_from_frags[0].m_signature = 2
        blocks_whole_from_frags[0].m_x = int(max_avg_x)
        blocks_whole_from_frags[0].m_y = int(max_avg_y)
        blocks_whole_from_frags[0].m_width = estimated_width
        blocks_whole_from_frags[0].m_height = pixy2_i_note_sz[note_cell].i_height
        blocks_whole_from_frags[0].m_index = 99  # special
        blocks_whole_from_frags[0].angle = 0
        blocks_whole_from_frags[0].m_age = 123  # special
        w_blk_count_from_frags = 1

        pixy2NtLog.info('Whole blk detected from [%d] Fragments: [X=%3d Y=%3d W=%d H=%d]' % (
        max_frags, blocks_whole_from_frags[0].m_x, blocks_whole_from_frags[0].m_y, blocks_whole_from_frags[0].m_width,
        blocks_whole_from_frags[0].m_height))

    else:
        pixy2NtLog.warning('No fragments could be coalesced')

    return (w_blk_count_from_frags, blocks_whole_from_frags)


# subroutine to filter blocks from pixy
def my_blocks_filtered(arg_count, arg_blocks):
    w_blk_count = 0
    blocks_whole = []

    f_blk_count = 0
    block_frags = []

    f_to_w_blk_count = 0
    f_to_w_blocks = []

    for i in range(0, arg_count):
        if arg_blocks[i].m_signature != 2:
            pixy2NtLog.debug('block sig not valid')
            continue

        (is_whole_note, is_note_too_big, is_frag_note) = block_is_match_w_whole_note(arg_blocks[i].m_x,
                                                                                     arg_blocks[i].m_y,
                                                                                     arg_blocks[i].m_width,
                                                                                     arg_blocks[i].m_height)

        if (is_whole_note == True):
            # detected block matches note size; take this block.
            pixy2NtLog.info('Match Result: detected block %d matches note size' % (i))
            blocks_whole.append(arg_blocks[i])
            w_blk_count = w_blk_count + 1

        elif (is_frag_note == True):
            pixy2NtLog.debug('Fragment: detected block %d is fragmented' % (i))
            # store the fragment for now
            block_frags.append(arg_blocks[i])
            f_blk_count = f_blk_count + 1

        else:
            pixy2NtLog.warning('detected block %d too big; discard' % (i))

    # if whole note is already detected, then ignore the fragments in the field of view
    if (w_blk_count == 0):
        # now walk through fragments, check if parts of a note and coalesce
        f_to_w_blk_count, f_to_w_blocks = block_coalesce_fragments(f_blk_count, block_frags)
        for i in range(0, f_to_w_blk_count):
            blocks_whole.append(Blocks(2, 0, 0, 0, 0, 0, 0, 123))
            blocks_whole[w_blk_count].m_signature = f_to_w_blocks[i].m_signature
            blocks_whole[w_blk_count].m_x = f_to_w_blocks[i].m_x
            blocks_whole[w_blk_count].m_y = f_to_w_blocks[i].m_y
            blocks_whole[w_blk_count].m_width = f_to_w_blocks[i].m_width
            blocks_whole[w_blk_count].m_height = f_to_w_blocks[i].m_height
            blocks_whole[w_blk_count].m_index = f_to_w_blocks[i].m_index
            blocks_whole[w_blk_count].m_angle = f_to_w_blocks[i].m_angle
            blocks_whole[w_blk_count].m_age = f_to_w_blocks[i].m_age
            w_blk_count += 1
    else:
        pixy2NtLog.debug('ignoring fragments, since whole block already detected')

    return w_blk_count, blocks_whole


##########################
# Main program 
##########################

print("client networktables initialization")
logging.basicConfig(level=logging.DEBUG)

#
# create another log file for logging this program run prints
#
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler = logging.FileHandler(strftime("/home/pi/CRESCENDO_2024/pixy2_nt_logs_%H_%M_%m_%d_%Y.log"), 'w')
handler.setFormatter(formatter)
pixy2NtLog = logging.getLogger('logToFile')

####### TO DISABLE LOGGING set level to logging.CRITICAL
# pixy2NtLog.setLevel(logging.DEBUG)
pixy2NtLog.setLevel(logging.INFO)
# pixy2NtLog.setLevel(logging.CRITICAL)

pixy2NtLog.addHandler(handler)

if len(sys.argv) != 2:
    print("Error: specify an IP to connect to!")
    exit(0)

ip = sys.argv[1]

NetworkTables.initialize(server=ip)


class SomeClient(object):
    """Demonstrates an object with magic networktables properties"""

    robotTime = ntproperty("/Pixy2/robotTime", 0, writeDefault=False)

    dsTime = ntproperty("/Pixy2/dsTime", 0)

    # block information
    blkSignature = ntproperty("/Pixy2/Signature", 0)
    blkX = ntproperty("/Pixy2/X", 0)
    blkY = ntproperty("/Pixy2/Y", 0)
    blkWidth = ntproperty("/Pixy2/Width", 0)
    blkHeight = ntproperty("/Pixy2/Height", 0)
    blkAge = ntproperty("/Pixy2/Age", 0)
    blkAngle = ntproperty("/Pixy2/AngleDeg", 0)
    blkValid = ntproperty("/Pixy2/Valid", False)
    timeStamp = ntproperty("/Pixy2/TimeStamp", "0")

#Initializing networktable client
nt_client = SomeClient()

# auto calibrate pixy2 to find ideal note dimensions
# Note: during first few seconds hold the camera steady with only a note at the center of camera Fov
# Todo


get_blk_frame = 0
nt_frame = 0
i = 0

while True:

    # equivalent to wpilib.SmartDashboard.putNumber('dsTime', i)
    nt_client.dsTime = i
    time.sleep(get_blk_interval)  # sleep for X ms before calling pixy again
    i += 1
    my_datetime = datetime.today()

    # clear old data
    del local_raw_blocks[:]
    raw_count = 0

    # Pixycam get_block data: increment get block call count
    get_blk_frame = get_blk_frame + 1

    # get detected blocks from pixycam
    raw_count = pixy.ccc_get_blocks(10, raw_blocks)
    
    if raw_count > 0:
        pixy2NtLog.info('\n')
        pixy2NtLog.debug('get_blk_frame [%3d]:' % (get_blk_frame))
        pixy2NtLog.debug('get blocks count = %d' % (raw_count))

        for index in range(0, raw_count):
            pixy2NtLog.info('[RAW BLOCK[%d]: SIG=%d X=%3d Y=%3d WIDTH=%3d HEIGHT=%3d AGE=%3d]' % (
            index, raw_blocks[index].m_signature, raw_blocks[index].m_x, raw_blocks[index].m_y,
            raw_blocks[index].m_width, raw_blocks[index].m_height, raw_blocks[index].m_age))

    else:
        # pixy2NtLog.debug('no raw blocks found')
        nt_client.timeStamp = str(my_datetime)
        nt_client.blkValid = False

        # get next set of blocks from pixy
        continue

    #
    # found blocks from pixy; process them
    #

    # first thing copy pixy blocks to our local block array strucure
    for index in range(0, raw_count):
        local_raw_blocks.append(Blocks(raw_blocks[index].m_signature, raw_blocks[index].m_x, raw_blocks[index].m_y,
                                       raw_blocks[index].m_width, raw_blocks[index].m_height, raw_blocks[index].m_angle,
                                       raw_blocks[index].m_index, raw_blocks[index].m_age))

    #
    # filtering blocks
    #
    count, blocks = my_blocks_filtered(raw_count, local_raw_blocks)
    pixy2NtLog.debug('filtered blocks count = %d' % (count))

    if count > 0:
        nt_frame = nt_frame + 1
        pixy2NtLog.debug('nt_frame [%3d]:' % (nt_frame))

        for index in range(0, count):
            # calculate block angle from center of FoV

            if blocks[index].m_y <= 208:
                # blkAngle = math.degrees(math.atan((158.0 - blocks[index].m_x)/(208.0 - blocks[index].m_y)))
                blkAngle = (158 - blocks[index].m_x) / 5.27
            else:
                blkAngle = 180  # invalid value
            if (blkAngle > max_angle_filter) or (blkAngle < -max_angle_filter):
                pixy2NtLog.warning('Block[%d] : angle  [%d] out of range' % (index, blkAngle))
                continue

            if blocks[index].m_signature != 2:
                pixy2NtLog.warning('Block[%d] sig not valid' % (index))
                continue

            # setting networktable block parameters
            nt_client.blkSignature = blocks[index].m_signature
            nt_client.blkX = blocks[index].m_x
            nt_client.blkY = blocks[index].m_y
            nt_client.blkWidth = blocks[index].m_width
            nt_client.blkHeight = blocks[index].m_height
            nt_client.blkAge = blocks[index].m_age
            nt_client.blkAngle = blkAngle
            nt_client.blkValid = True
            nt_client.timeStamp = str(my_datetime)

            pixy2NtLog.info(
                '[NW Table BLOCK[%d]: SIG=%d X=%3d Y=%3d WIDTH=%3d HEIGHT=%3d AGE=%3d Angle=%3d degrees TimeStamp=%s]' % (
                index, blocks[index].m_signature, blocks[index].m_x, blocks[index].m_y, blocks[index].m_width,
                blocks[index].m_height, blocks[index].m_age, nt_client.blkAngle, nt_client.timeStamp))
            # putting into networktables

            # sending only one block
            break

    else:
        # print('no filtered blocks found')
        nt_client.blkValid = False
        nt_client.timeStamp = str(my_datetime)
