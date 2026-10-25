"""Remove the HCLK -> PLL pips that chipdb.py does not create from an existing chip database.

The database is built from the Gowin IDE files. An IDE without some packages builds a database
without their package and pin data, so instead of building it again this takes a released
.msgpack.xz and drops only what fse_create_hclk_nodes leaves out: every HCLK pip into a PLL
input that _hclk_to_pll does not list, the PLL cell's wires in the HCLK_OUT nodes, the copies in
extra_func and the HAS_PLL_HCLK flag.

usage: python -m apycula.strip_pll_hclk_pips DEVICE IN.msgpack.xz OUT.msgpack.xz
"""
import argparse
import os
import sys

from apycula import chipdb

_pll_bels = {'RPLLA', 'PLLVR'}


def pll_side(dev, row, col):
    """ The side of the chip the PLL cell is on, as in fse_create_hclk_nodes """
    if row == 0:
        return 'T'
    if row == dev.rows - 1:
        return 'B'
    if col == 0:
        return 'L'
    if col == dev.cols - 1:
        return 'R'
    return None


def strip(dev, device):
    removed = []
    for (row, col), pips in list(dev.hclk_pips.items()):
        bels = _pll_bels & dev[row, col].bels.keys()
        if not bels:
            continue
        portmap = dev[row, col].bels[bels.pop()].portmap
        # dat_portmap renames PLL_CLKIN/PLL_CLKFB to the PLL's port wires (rPLL only)
        names = {'PLL_CLKIN': 'PLL_CLKIN', 'PLL_CLKFB': 'PLL_CLKFB',
                 portmap.get('CLKIN'): 'PLL_CLKIN', portmap.get('CLKFB'): 'PLL_CLKFB'}
        allowed = chipdb._hclk_to_pll.get(device, {}).get(pll_side(dev, row, col), {})
        for dst in [d for d in pips if d in names]:
            for src in [s for s in pips[dst] if s not in allowed.get(names[dst], set())]:
                del pips[dst][src]
                removed.append((row, col, dst, src))
            if not pips[dst]:
                del pips[dst]
        # a source wire stays in its node only while another pip of the cell uses it
        used = set(pips) | {src for srcs in pips.values() for src in srcs}
        for r, c, _, src in [x for x in removed if x[:2] == (row, col)]:
            if src not in used:
                for _, wires in dev.nodes.values():
                    wires.discard((r, c, src))
        if not pips:
            del dev.hclk_pips[row, col]
        # extra_func carries a copy of the cell's hclk pips (sync_extra_func)
        extra = dev.extra_func.get((row, col))
        if extra is not None:
            if (row, col) in dev.hclk_pips:
                extra['hclk_pips'] = dev.hclk_pips[row, col]
            else:
                extra.pop('hclk_pips', None)
                if not extra:
                    del dev.extra_func[row, col]
    if device not in chipdb._hclk_to_pll and 'HAS_PLL_HCLK' in dev.chip_flags:
        dev.chip_flags.remove('HAS_PLL_HCLK')
    return removed


def main():
    # sets are written in iteration order, which depends on the string hash seed: a fixed seed
    # gives the same file on every run
    if os.environ.get('PYTHONHASHSEED') != '0':
        os.environ['PYTHONHASHSEED'] = '0'
        os.execv(sys.executable, [sys.executable, '-m', __spec__.name] + sys.argv[1:])
    parser = argparse.ArgumentParser(description='Remove HCLK -> PLL pips not listed in _hclk_to_pll')
    parser.add_argument('device')
    parser.add_argument('input')
    parser.add_argument('output')
    args = parser.parse_args()

    dev = chipdb.load_chipdb(args.input)
    removed = strip(dev, args.device)
    for row, col, dst, src in removed:
        print(f'removed X{col}Y{row}/{dst} <- {src}')
    print(f'{len(removed)} pips removed, flags {sorted(dev.chip_flags)}')
    chipdb.save_chipdb(dev, args.output)


if __name__ == '__main__':
    main()
