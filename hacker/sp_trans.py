import struct
import sys

def process_spectro_file(input_path):
    """Read a spectrophotometer binary file, decode its data, and save as CSV."""
    output_path = input_path.rsplit('.', 1)[0] + ".csv"
    with open(input_path, 'rb') as f, open(output_path, 'w') as out:
        content = f.read()
        # 1. Skip the ASCII header (file identifier)
        # Find the position of ".WAV" and the following null byte
        header_end = 0
        idx = content.find(b'.WAV')
        if idx != -1:
            null_pos = content.find(b'\x00', idx)
            if null_pos != -1:
                header_end = null_pos + 1  # end of "X.WAV\0"
        # 2. Find end-of-header pattern (0.0, 3.0 as 8-byte float sequence)
        pattern = b'\x00\x00\x00\x00\x40\x40\x00\x00'  # 0.0 and 3.0 in big-endian float
        pat_idx = content.find(pattern, header_end)
        if pat_idx != -1:
            header_end = pat_idx + len(pattern)
        else:
            # If pattern not found, assume a default header length to be safe
            header_end = max(header_end, 100)  # e.g., skip at least 100 bytes
        # 3. Extract data bytes after the header
        data_bytes = content[header_end:]
        data_point_count = 0
        wavelengths = []
        values = []
        # 3a. Determine data format
        data_type = None
        n = len(data_bytes)
        if n % 4 == 0 and n > 0:
            data_point_count = n // 4
            # Try interpreting as float32 (little-endian vs big-endian)
            floats_le = struct.unpack('<' + 'f'*data_point_count, data_bytes)
            floats_be = struct.unpack('>' + 'f'*data_point_count, data_bytes)
            # Heuristic: choose the interpretation with more plausible values
            # (e.g., absorbance typically 0-5 and rarely NaN; transmittance 0-100)
            def score_float_array(arr):
                valid_vals = 0
                for x in arr:
                    if x != float('inf') and x != float('-inf') and not (x != x):  # not NaN
                        # count values in a reasonable range
                        if -1000 < x < 1000:
                            valid_vals += 1
                return valid_vals
            score_le = score_float_array(floats_le)
            score_be = score_float_array(floats_be)
            if score_be >= score_le:
                values = list(floats_be)
                data_type = 'float32_be'
            else:
                values = list(floats_le)
                data_type = 'float32_le'
        elif n % 2 == 0 and n > 0:
            # If not 4-byte aligned, try 2-byte int16
            data_point_count = n // 2
            ints = struct.unpack('<' + 'H'*data_point_count, data_bytes)  # assuming unsigned 16-bit
            values = list(ints)
            data_type = 'int16'
        else:
            # Fallback: treat as bytes
            data_point_count = n
            values = list(data_bytes)
            data_type = 'bytes'
        # 4. Generate wavelength axis
        if data_type.startswith('float32'):
            # Attempt to retrieve start and end wavelengths from header if present
            start_wl = end_wl = None
            # The 8 bytes immediately before the (0.0,3.0) pattern are [start_wl, end_wl] in big-endian float
            if pat_idx != -1:
                try:
                    start_wl = struct.unpack('>f', content[pat_idx-8:pat_idx-4])[0]
                    end_wl   = struct.unpack('>f', content[pat_idx-4:pat_idx])[0]
                except Exception:
                    start_wl = end_wl = None
            # Default to index range if not found
            if start_wl is None or end_wl is None:
                start_wl = 0.0
                end_wl = float(data_point_count - 1)
            # Compute wavelengths for each data point
            step = (end_wl - start_wl) / (data_point_count - 1) if data_point_count > 1 else 0
            wavelengths = [start_wl + i*step for i in range(data_point_count)]
        else:
            # If data is integer or unknown, we may not have explicit wavelength info
            wavelengths = list(range(data_point_count))
        # 5. Write output CSV (with header row)
        out.write("Wavelength,Absorbance\n")
        for wl, val in zip(wavelengths, values):
            out.write(f"{wl:.3f},{val:.6f}\n")
    print(f"Processed {input_path} ({data_type}), saved {output_path}")

# --- Command-line interface ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_spectro.py <file1> [<file2> ...]")
        sys.exit(1)
    for filepath in sys.argv[1:]:
        try:
            process_spectro_file(filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")