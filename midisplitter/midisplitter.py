#! /usr/bin/python3

r'''###############################################################################
###################################################################################
#
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

from .constants import Number2patch, Number2drumkit

from .MIDI import midi2ms_score, score2midi

###################################################################################
###################################################################################

def compute_sustain_intervals(events):

    """
    Identify and merge consecutive sustain pedal intervals from velocity events.
    
    Filters events where velocity >= 64 to detect pedal press and release times,
    records the start time of each press and end time of the corresponding release,
    and merges touching or overlapping intervals to provide continuous durations.
    
    Parameters
    ----------
    events : list of tuple
        A list of (time, velocity) pairs representing MIDI velocity events over time.
    
    Returns
    ------
    list of tuple
        A list of (start_time, end_time) tuples representing merged sustain intervals.
        End times are the actual release time or infinity if the pedal is never released.
    
    Notes
    -----
    An interval is considered to start when a velocity >= 64 is received without
    a previously open interval, and ends when velocity < 64 is received.
    Adjacent or overlapping intervals are automatically merged into a single interval.
    """

    intervals = []
    pedal_on = False
    current_start = None
    
    for t, cc in events:
        if not pedal_on and cc >= 64:

            pedal_on = True
            current_start = t
        elif pedal_on and cc < 64:

            pedal_on = False
            intervals.append((current_start, t))
            current_start = None

    if pedal_on:
        intervals.append((current_start, float('inf')))

    merged = []
    
    for interval in intervals:
        if merged and interval[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], interval[1]))
        else:
            merged.append(interval)
    return merged

###################################################################################

def apply_sustain_to_ms_score(score):

    """
    Apply sustain pedal intervals to midi score durations.
    
    Analyzes control change events (CC64) to identify sustain pedal presses and releases,
    calculates effective note durations by extending them to the pedal release or the end of the piece,
    and updates the note durations in the provided score.
    
    Args:
        score (list): A list representing a Midi Score, where each element is a Track tuple:
                      ((track_name, is_midi3), [list of events]).
                      Events are tuples: (event_type, time, channel, data1, data2).
                      event_type: 'note', 'control_change', etc.
                      For 'note' events: time is timestamp, data2 is nominal duration.
    
    Returns:
        list: The modified score with updated note durations.
    
    Notes:
        - Infinite intervals (pedal held to end of score) are resolved based on a computed
          global maximum offset derived from instrument velocity values.
        - Only channels with active sustain intervals will have their notes extended.
        - Intervals are only extended backward if the note starts within the sustain duration;
          currently, the implementation extends the note off-time to match the end of the sustain
          interval if the note's nominal off-time falls within the interval.
    """

    sustain_by_channel = {}
    
    for track in score[1:]:
        for event in track:
            if event[0] == 'control_change' and event[3] == 64:
                channel = event[2]
                sustain_by_channel.setdefault(channel, []).append((event[1], event[4]))
    
    sustain_intervals_by_channel = {}
    
    for channel, events in sustain_by_channel.items():
        events.sort(key=lambda x: x[0])
        sustain_intervals_by_channel[channel] = compute_sustain_intervals(events)
    
    global_max_off = 0
    
    for track in score[1:]:
        for event in track:
            if event[0] == 'note':
                global_max_off = max(global_max_off, event[1] + event[2])
                
    for channel, intervals in sustain_intervals_by_channel.items():
        updated_intervals = []
        for start, end in intervals:
            if end == float('inf'):
                end = global_max_off
            updated_intervals.append((start, end))
        sustain_intervals_by_channel[channel] = updated_intervals
        
    if sustain_intervals_by_channel:
        
        for track in score[1:]:
            for event in track:
                if event[0] == 'note':
                    start = event[1]
                    nominal_dur = event[2]
                    nominal_off = start + nominal_dur
                    channel = event[3]
                    
                    intervals = sustain_intervals_by_channel.get(channel, [])
                    effective_off = nominal_off
        
                    for intv_start, intv_end in intervals:
                        if intv_start < nominal_off < intv_end:
                            effective_off = intv_end
                            break
                    
                    effective_dur = effective_off - start
                    
                    event[2] = effective_dur

    return score

###################################################################################

instrument_name = lambda s: ''.join(c for c in s.lower() if c.isalpha() or c==' ').strip().replace('  ', '_').replace(' ', '_')

###################################################################################

def split_midi(midi_file, output_dir=None):
    
    """
    Split a multi-track MIDI file into per‑channel, per‑instrument MIDI stems.

    This function loads a MIDI file in TMIDIX ms-score format, normalizes and
    cleans each track, applies sustain‑pedal expansion, and extracts all
    note‑bearing channels as independent musical “voices.” Each resulting voice
    is written as its own single‑track MIDI file with a standardized header,
    a fixed tempo (1,000,000 µs per quarter), a default 4/4 time signature,
    a track name, and a program/patch assignment.

    Processing steps:
    - Parse the MIDI into ms‑score format and extract ticks-per-beat and tracks.
    - Normalize channel numbers and pitch/velocity ranges for notes and
      patch‑change events.
    - Apply sustain‑pedal logic to each track to ensure correct note durations.
    - Remove all non-musical events except: note, patch_change, track_name.
    - For each track, detect all channels that contain notes.
    - For each channel:
        * Collect all notes belonging to that channel.
        * Determine the effective program/patch for that channel, including
          drum‑kit offsets for channel 9.
        * Rebase all events to channel 0 for output.
        * Build a new single‑track score with a clean header and patch assignment.
        * Write the result as a standalone MIDI file.

    Output naming:
    - Files are named as:
        "{index:03d}_{instrument_name}_{patch}.mid"
      where `instrument_name` is derived from the GM program number or drum‑kit
      mapping. Drum kits use patch numbers ≥128.

    Parameters
    ----------
    midi_file : str or Path
        Path to the input MIDI file.
    output_dir : str or Path, optional
        Directory where the split MIDI stems will be written. If None, files
        are written to the current working directory.

    Returns
    -------
    None
        The function writes one MIDI file per detected channel/voice and
        performs no in‑memory return of the split data.

    Notes
    -----
    - Each output file contains exactly one musical voice (one channel’s notes).
    - All output stems share the same fixed tempo and time signature.
    - Drum channels are mapped to GM drum kits when possible; otherwise a
      “custom_kit” label is used.
    """
    
    raw_score = midi2ms_score(open(midi_file, 'rb').read())
    
    # ----------------------------------------------------------------------------

    num_ticks = raw_score[0]

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
        
        apply_sustain_to_ms_score([num_ticks, new_track])

        all_clean_tracks.append([e for e in new_track if e[0] in ['note', 'patch_change', 'track_name']])
        
    # ----------------------------------------------------------------------------

    all_scores = []

    for i, track in enumerate(all_clean_tracks):
        
        track_names = [e for e in track if e[0] == 'track_name']
        track_name = track_names[0][2] if track_names else 'Track #' + str(i)
        
        track_patches = [0] * 16

        for e in track:
            if e[0] == 'patch_change':
                track_patches[e[2]] = e[3] if e[2] != 9 else e[3]+128

        track_chans = sorted(set([e[3] for e in track if e[0] == 'note']))
                
        for cha in track_chans:
            score = []

            for e in track:
                if e[0] == 'note' and e[3] == cha:
                    score.append(e)
                    
            if score:
                all_scores.append([track_name, track_patches[cha], score])
    
    # ----------------------------------------------------------------------------
    
    if all_scores:

        for i, (tname, tpat, score) in enumerate(all_scores):

            new_score = copy.deepcopy(score)

            for e in new_score:
                e[3] = 0

            output_header = [['set_tempo', 0, 1000000],
                             ['time_signature', 0, 4, 2, 24, 8],
                             ['track_name', 0, tname],
                             ['patch_change', 0, 0, tpat]
                            ]

            output = [1000, output_header + new_score]
            
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

print('Module is loaded!')
print('Enjoy! :)')
print('=' * 70)

###################################################################################
# This is the end of the midisplitter Python module
###################################################################################