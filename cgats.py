"""
CGATS (Committee for Graphic Arts Technologies Standards) file parser.
Handles .ti1, .ti2, .ti3 and .cal files used by ArgyllCMS.
"""

import re
from pathlib import Path


class CGATSFile:
    """Parser for CGATS format files (.ti1, .ti2, .ti3, .cal)."""

    def __init__(self):
        self.keywords = {}      # keyword -> value
        self.fields = []        # ordered list of field names
        self.data = []          # list of dicts keyed by field name
        self.other_tables = []  # additional data tables (some files have multiple)

    @classmethod
    def parse(cls, filepath):
        """Parse a CGATS file and return a CGATSFile instance."""
        obj = cls()
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"CGATS file not found: {filepath}")

        text = filepath.read_text(encoding='utf-8', errors='replace')
        lines = text.splitlines()

        i = 0
        table_num = 0

        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line or line.startswith('#'):
                continue

            # BEGIN_DATA_FORMAT
            if line == 'BEGIN_DATA_FORMAT':
                fields = []
                while i < len(lines):
                    fline = lines[i].strip()
                    i += 1
                    if fline == 'END_DATA_FORMAT':
                        break
                    fields.extend(fline.split())

                if table_num == 0:
                    obj.fields = fields
                else:
                    obj.other_tables.append({'fields': fields, 'data': []})
                continue

            # BEGIN_DATA
            if line == 'BEGIN_DATA':
                current_fields = obj.fields if table_num == 0 else obj.other_tables[-1]['fields']
                current_data = []
                while i < len(lines):
                    dline = lines[i].strip()
                    i += 1
                    if dline == 'END_DATA':
                        break
                    if not dline or dline.startswith('#'):
                        continue
                    values = dline.split()
                    if len(values) >= len(current_fields):
                        row = {}
                        for fi, fname in enumerate(current_fields):
                            val = values[fi]
                            row[fname] = _parse_value(val)
                        current_data.append(row)

                if table_num == 0:
                    obj.data = current_data
                else:
                    obj.other_tables[-1]['data'] = current_data

                table_num += 1
                continue

            # Keyword/value pairs
            match = re.match(r'^(\w+)\s+"([^"]*)"', line)
            if match:
                obj.keywords[match.group(1)] = match.group(2)
                continue

            match = re.match(r'^(\w+)\s+(.*)', line)
            if match:
                key = match.group(1)
                val = match.group(2).strip().strip('"')
                obj.keywords[key] = _parse_value(val)
                continue

        return obj

    def get_color_space(self):
        """Return the color space string (e.g. 'CMYK', 'RGB')."""
        cs = self.keywords.get('COLOR_REP', '')
        if '_' in cs:
            return cs.split('_')[0]
        return cs

    def get_device_fields(self):
        """Return list of device value field names."""
        cs = self.get_color_space().upper()
        mapping = {
            'CMYK': ['CMYK_C', 'CMYK_M', 'CMYK_Y', 'CMYK_K'],
            'RGB':  ['RGB_R', 'RGB_G', 'RGB_B'],
            'CMY':  ['CMY_C', 'CMY_M', 'CMY_Y'],
        }
        if cs in mapping:
            return [f for f in mapping[cs] if f in self.fields]
        # Fallback: find fields matching common patterns
        dev_fields = [f for f in self.fields if any(
            f.startswith(p) for p in ['CMYK_', 'RGB_', 'CMY_']
        )]
        return dev_fields

    def get_cie_fields(self):
        """Return list of CIE value field names (XYZ or Lab)."""
        cie = [f for f in self.fields if f.startswith('XYZ_') or f.startswith('LAB_')]
        return cie

    def get_patch_locations(self):
        """Return dict mapping SAMPLE_ID -> SAMPLE_LOC (e.g. 'A1', 'B5')."""
        if 'SAMPLE_LOC' not in self.fields:
            return {}
        return {
            row.get('SAMPLE_ID', row.get('SampleID', idx)): row['SAMPLE_LOC']
            for idx, row in enumerate(self.data)
        }

    def get_strip_layout(self):
        """Parse patch locations into strip structure.
        Returns dict: strip_label -> list of (patch_index, patch_label, row_data)
        """
        locations = {}
        for idx, row in enumerate(self.data):
            loc = row.get('SAMPLE_LOC', '')
            if not loc:
                continue
            # Location format is like "A1", "AA5", etc.
            match = re.match(r'^([A-Z]+)(\d+)$', loc)
            if match:
                strip = match.group(1)
                patch_num = int(match.group(2))
                if strip not in locations:
                    locations[strip] = []
                locations[strip].append((idx, patch_num, loc, row))

        # Sort patches within each strip by patch number
        for strip in locations:
            locations[strip].sort(key=lambda x: x[1])

        return locations

    def get_num_patches(self):
        """Return number of patches/samples."""
        n = self.keywords.get('NUMBER_OF_SETS', None)
        if n is not None:
            return int(n)
        return len(self.data)

    def get_device_values(self, row):
        """Extract device values from a data row as list of floats."""
        return [float(row.get(f, 0)) for f in self.get_device_fields()]

    def get_xyz_values(self, row):
        """Extract XYZ values from a data row."""
        return [float(row.get(f, 0)) for f in ['XYZ_X', 'XYZ_Y', 'XYZ_Z']
                if f in row]

    def get_lab_values(self, row):
        """Extract Lab values from a data row."""
        return [float(row.get(f, 0)) for f in ['LAB_L', 'LAB_A', 'LAB_B']
                if f in row]


def _parse_value(s):
    """Try to parse a string as int, float, or leave as string."""
    try:
        if '.' in s or 'e' in s.lower():
            return float(s)
        return int(s)
    except (ValueError, AttributeError):
        return s
