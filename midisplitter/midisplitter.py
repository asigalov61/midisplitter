#! /usr/bin/python3

r'''###############################################################################
###################################################################################
#
#	MIDI Splitter Python Module
#	Version 1.0
#
#	Project Los Angeles
#
#	Tegridy Code 2026
#
#   https://github.com/Tegridy-Code/Project-Los-Angeles
#
###################################################################################
###################################################################################
#
#   Copyright 2026 Project Los Angeles / Tegridy Code
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
###################################################################################
'''

###################################################################################
###################################################################################

print('=' * 70)
print('Loading midisplitter Python module...')
print('Please wait...')
print('=' * 70)

__version__ = '1.0.0'

print('midisplitter module version', __version__)
print('=' * 70)

###################################################################################
###################################################################################

import os
import copy
import statistics

from .constants import Number2patch, Number2drumkit

from .MIDI import midi2score, score2midi

###################################################################################
###################################################################################

special_events = ['key_after_touch',
                  'control_change',
                  'channel_after_touch',
                  'pitch_wheel_change'
                 ]

special_merge_events = ['key_after_touch',
                        'control_change',
                        'patch_change',
                        'channel_after_touch',
                        'pitch_wheel_change'
                       ]

###################################################################################

instrument_name = lambda s: ''.join(c for c in s.lower().replace('(', ' ').replace(')', ' ').strip()
                                    if c.isalpha() or c==' ').strip().replace('  ', '_').replace(' ', '_')

###################################################################################

def set_of_sublists(list_of_lists):
    seen = set()
    add = seen.add
    
    for sub in list_of_lists:
        add(tuple(sub))
        
    return [list(t) for t in seen]

###################################################################################

def split_midi(midi_file, output_dir=None):
    
    """
    Split a MIDI file into per‑instrument stems by analyzing channels, program
    changes, and event types, then write each stem as an individual MIDI file.

    This function performs a deterministic, channel‑aware decomposition of a
    multi‑track MIDI score into separate instrument stems. Each stem contains:

    - All NOTE events belonging to a single channel within a single track.
    - All channel‑specific expressive events (key aftertouch, control change,
      channel aftertouch, pitch‑wheel) that target the same channel.
    - All global, non‑channel events (e.g., track_name, meta events) merged
      across tracks and preserved in every output stem.
    - A single program assignment derived from the most recent patch_change
      event on that channel, with GM drum‑kit remapping for channel 9.

    Processing steps
    ----------------
    1. Load the MIDI file using `midi2score` and extract ticks-per-beat and
       track event lists.
    2. Normalize NOTE and PATCH_CHANGE fields to valid MIDI ranges
       (channels mod 16, velocities mod 128, programs mod 128).
    3. For each track:
       - Determine its human-readable name (or fallback to "Track #i").
       - Build a per-channel program table from patch_change events.
       - Collect all non-note, non-patch, non-expressive events as global
         "other events" to be shared across all stems.
       - Identify all channels that contain NOTE events.
       - For each such channel, extract:
         • NOTE events for that channel
         • expressive events targeting that channel
         • all global non-expressive events
         producing one stem candidate.
    4. For each stem:
       - Merge in all global events from all tracks.
       - Sort events by absolute time.
       - Rewrite channel numbers to 0 for pitched instruments, or to 9 for
         drum kits, depending on the resolved program.
       - Construct a minimal header containing track_name and a single
         patch_change event.
       - Convert the score back to MIDI bytes via `score2midi`.
       - Generate a filename of the form:
         "{index}_{instrument_name}_{program}.mid"
         using GM instrument or drum‑kit names.

    Output
    ------
    For each detected (track, channel) instrument stem, a `.mid` file is written
    either into `output_dir` (created if necessary) or into the current working
    directory. Filenames encode the stem index, normalized instrument name, and
    program number.

    Parameters
    ----------
    midi_file : str or Path
        Path to the input MIDI file.
    output_dir : str or Path, optional
        Directory in which to write the generated stems. If None, files are
        written next to the input file.

    Notes
    -----
    - Channel 9 (GM drums) is mapped to program numbers 128–255 internally to
      distinguish drum kits; these are remapped back to channel 9 on output.
    - All stems share the same ticks-per-beat value from the original file.
    - Event ordering is strictly time‑sorted after merging global events.
    - This function writes files to disk and returns nothing.
    """
    
    raw_score = midi2score(open(midi_file, 'rb').read())
    
    # ----------------------------------------------------------------------------

    midi_ticks = raw_score[0]
    
    all_tracks = raw_score[1:]

    all_clean_tracks = []

    for track in all_tracks:
        new_track = copy.deepcopy(track)
        for e in new_track:
        
          if e[0] == 'note':
              e[3] = e[3] % 16
              e[4] = e[4] % 128
              e[5] = e[5] % 128
        
          if e[0] == 'patch_change':
              e[2] = e[2] % 16
              e[3] = e[3] % 128

        all_clean_tracks.append(new_track)
        
    # ----------------------------------------------------------------------------

    all_scores = []
    all_other_events = []

    for i, track in enumerate(all_clean_tracks):
        
        track_names = [e for e in track if e[0] == 'track_name']
        track_name = track_names[0][2] if track_names else 'Track #' + str(i)
        
        track_patches = [0] * 16

        for e in track:
            if e[0] == 'patch_change':
                track_patches[e[2]] = e[3] if e[2] != 9 else e[3]+128

        other_events = [e for e in track if e[0] != 'note' and e[0] != 'patch_change' and e[0] not in special_events]
        all_other_events.extend(other_events)

        track_chans = sorted(set([e[3] for e in track if e[0] == 'note']))
                
        for cha in track_chans:
            score = []

            for e in track:
                if e[0] == 'note' and e[3] == cha:
                    score.append(e)
                    
                if e[0] in special_events and e[2] == cha:
                    score.append(e)

                if e[0] != 'note' and e[0] not in special_events:
                    score.append(e)
   
            if score:
                all_scores.append([track_name, track_patches[cha], score])
    
    # ----------------------------------------------------------------------------
    
    if all_scores:

        for i, (tname, tpat, score) in enumerate(all_scores):

            new_score = copy.deepcopy(score)

            new_score.extend(all_other_events)
            new_score.sort(key=lambda x: x[1])
            
            if tpat < 128:
                for e in new_score:
                    if e[0] == 'note':
                        e[3] = 0

                    if e[0] in special_events:
                        e[2] = 0

            output_header = [['track_name', 0, tname]]
            
            if tpat < 128:
                output_header.append(['patch_change', 0, 0, tpat])
                
            else:
                output_header.append(['patch_change', 0, 9, tpat-128])

            output = [midi_ticks, output_header + new_score]
            
            midi_data = score2midi(output)

            if tpat < 128:
                output_file_name = str(i).zfill(3) + '_' + instrument_name(Number2patch[tpat]) + '_' + str(tpat)

            else:
                dpat = tpat - 128

                if dpat in Number2drumkit:
                    output_file_name = str(i).zfill(3) + '_' + instrument_name(Number2drumkit[dpat]) + '_' + str(dpat)

                else:
                    output_file_name = str(i).zfill(3) + '_' + 'custom_kit' + '_' + str(dpat)
                    
            output_file_name += '.mid'
                    
            if output_dir is not None:
                os.makedirs(output_dir, exist_ok=True)
                
                output_file_name = os.path.join(output_dir, output_file_name)
            
            with open(output_file_name, 'wb') as midi_file:
                midi_file.write(midi_data)
                midi_file.close()

###################################################################################

def merge_midis(midi_files_list: list,
                output_midi_name: str = 'merged.mid',
                output_midi_ticks: int = -1
                ):

    """
    Merges split MIDIs back into one MIDI
    """

    if midi_files_list:

        all_midi_scores = []
        
        for midi_file in midi_files_list:
            if os.path.isfile(midi_file):
                score = midi2score(open(midi_file, 'rb').read())

                if score and score[1]:
                    all_midi_scores.append(score)

        if all_midi_scores:
            if output_midi_ticks > 0:
                mticks = output_midi_ticks

            else:
                mticks = statistics.mode([s[0] for s in all_midi_scores])

            all_midi_scores_flat = []
    
            for cha, midi_score in enumerate(all_midi_scores):

                cha = cha % 15

                if cha == 9:
                    cha += 1
                
                for track in midi_score[1:]:
                    for e in track:
                        if e[0] == 'note' and e[3] != 9:
                            e[3] = cha

                        if e[0] in special_merge_events and e[2] != 9:
                            e[2] = cha
                            
                    all_midi_scores_flat.extend(track)

            final_score = sorted(set_of_sublists(all_midi_scores_flat),
                                 key= lambda x: x[1]
                                )

            final_score = [mticks, final_score]

            midi_data = score2midi(final_score)

            try:
                with open(output_midi_name, 'wb') as fi:
                    fi.write(midi_data)

            except:
                pass
                
###################################################################################

print('Module is loaded!')
print('Enjoy! :)')
print('=' * 70)

###################################################################################
# This is the end of the midisplitter Python module
###################################################################################