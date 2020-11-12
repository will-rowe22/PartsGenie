'''
PathwayGenie (c) GeneGenie Bioinformatics Ltd. 2018

PathwayGenie is licensed under the MIT License.

To view a copy of this license, visit <http://opensource.org/licenses/MIT/>.

@author:  neilswainston
'''
# pylint: disable=invalid-name
# pylint: disable=relative-beyond-top-level
# pylint: disable=too-many-arguments
import sys

from .writer import write


def do_write(in_filename, out_filename, ice_url, ice_username, ice_password,
             group_name=None):
    '''Write.'''
    comp_columns = ['plasmid', 'host']
    typ = 'STRAIN'
    write(in_filename, out_filename, ice_url, ice_username, ice_password,
          typ, comp_columns, group_name)


def main(args):
    '''main method.'''
    do_write(*args)


if __name__ == '__main__':
    main(sys.argv[1:])
