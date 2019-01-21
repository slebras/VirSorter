import os
import subprocess
import time
import glob
import uuid
import tarfile
from string import Template
import pandas as pd

from installed_clients.AssemblyUtilClient import AssemblyUtil
from installed_clients.DataFileUtilClient import DataFileUtil as dfu
from installed_clients.KBaseReportClient import KBaseReport


html_template = Template("""<!DOCTYPE html>
<html lang="en">
  <head>
    <link href="https://netdna.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.datatables.net/1.10.19/css/jquery.dataTables.min.css" rel="stylesheet">
    <script src="https://code.jquery.com/jquery-3.3.1.js" type="text/javascript"></script>
    <script src="https://cdn.datatables.net/1.10.19/js/jquery.dataTables.min.js" type="text/javascript"></script>
  </head>
  <body>
    <div class="container">
      <div>
        ${html_table}
      </div>
    </div>

    <script type="text/javascript">
      $$(document).ready(function() {
          $$('#my_id').DataTable();
      } );
      </script>
  </body>
</html>""")

def log(message, prefix_newline=False):
    """
    Logging function, provides a hook to suppress or redirect log messages.
    """
    print(('\n' if prefix_newline else '') + '{0:.2f}'.format(time.time()) + ': ' + str(message))


class VirSorterUtils:

    def __init__(self, config):
        self.scratch = os.path.abspath(config['scratch'])

    def VirSorter_help(self):
        command = 'wrapper_phage_contigs_sorter_iPlant.pl --help'
        self._run_command(command)

    def run_VirSorter(self, params):
        self.callback_url = os.environ['SDK_CALLBACK_URL']
        params['SDK_CALLBACK_URL'] = self.callback_url
        params['KB_AUTH_TOKEN'] = os.environ['KB_AUTH_TOKEN']

        # Get contigs from 'assembly'
        self.AssemblyUtil = AssemblyUtil(self.callback_url)
        genome_ret = self.AssemblyUtil.get_assembly_as_fasta({
            'ref': "23130/2/1"
        })

        genome_fp = genome_ret['path']

        command = 'wrapper_phage_contigs_sorter_iPlant.pl --data-dir /data/virsorter-data'

        # Add in first args
        command += ' -f {} --db {}'.format(genome_fp, params['database'])

        # if params['add_genomes'] == '1':
        #     command += ' --cp {}'.format()  # Add custom phage genomes, from where?

        bool_args = ['virome', 'diamond', 'keep_db', 'no_c']  # keep_db = keep-db

        for bool_arg in bool_args:
            if params[bool_arg] == 0:
                if bool_arg == 'keep_db':
                    bool_arg = 'keep-db'

                command += ' --{}'.format(bool_arg)

        self._run_command(command)

        report = self._generate_report(params)

        return report

    def _run_command(self, command):
        """

        :param command:
        :return:
        """

        log('Start executing command:\n{}'.format(command))
        pipe = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        output = pipe.communicate()[0]
        exitCode = pipe.returncode

        if (exitCode == 0):
            log('Executed command:\n{}\n'.format(command) +
                'Exit Code: {}\nOutput:\n{}'.format(exitCode, output))
        else:
            error_msg = 'Error running command:\n{}\n'.format(command)
            error_msg += 'Exit Code: {}Output:\n{}'.format(exitCode, output)

    def _parse_summary(self, virsorter_global_fp):
        columns = ['Contig_id', 'Nb genes contigs', 'Fragment', 'Nb genes', 'Category', 'Nb phage hallmark genes',
                   'Phage gene enrichment sig', 'Non-Caudovirales phage gene enrichment sig', 'Pfam depletion sig',
                   'Uncharacterized enrichment sig', 'Strand switch depletion sig', 'Short genes enrichment sig',
                   ]

        with open(virsorter_global_fp, 'r') as vir_fh:
            data = {}
            category = ''
            for line in vir_fh:
                if line.startswith('## Contig_id'):
                    continue
                elif line.startswith('## '):  # If 'header' lines are consumed by 1st if, then remaining should be good
                    category = line.split('## ')[-1].split(' -')[0]
                else:
                    values = line.strip().split(',')
                    data[values[0]] = dict(zip(columns[1:], values[1:]))

        df = pd.DataFrame().from_dict(data, orient='index')
        df.index.name = columns[0]
        df.reset_index(inplace=True)

        html = df.to_html(index=False, classes='my_class" id = "my_id')

        # Need to file write below
        direct_html = html_template.substitute(html_table=html)

        return direct_html

    def _generate_report(self, params):
        """

        :param params:
        :return:
        """

        # Get URL
        self.dfu = dfu(params['SDK_CALLBACK_URL'])

        # Output directory should be $PWD/virsorter-out
        virsorter_outdir = os.path.join(os.getcwd(), 'virsorter-out')

        # kb_deseq functions out adding output files, then building report files, then sending all of them
        # to the workspace
        output_files = []  # Appended list of dicts containing attributes

        # Collect all the files needed to report to end-user
        # Get all predicted viral sequences
        pred_fnas = glob.glob(os.path.join(virsorter_outdir, 'Predicted_viral_sequences/VIRSorter_*.fasta'))
        pred_gbs = glob.glob(os.path.join(virsorter_outdir, 'Predicted_viral_sequences/VIRSorter_*.gb'))
        # Summary 'table'
        glob_signal = os.path.join(virsorter_outdir, 'VIRSorter_global-phage-signal.csv')

        # ...
        output_dir = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_dir)

        # Deal with nucleotide fasta
        pred_fna_tgz_fp = os.path.join(output_dir, 'VIRSorter_predicted_viral_fna.tar.gz')
        with tarfile.open(pred_fna_tgz_fp, 'w:gz') as pred_fna_tgz_fh:
            for pred_fna in pred_fnas:
                pred_fna_tgz_fh.add(pred_fna, arcname=os.path.basename(pred_fna))
        output_files.append({
            'path': pred_fna_tgz_fp,
            'name': os.path.basename(pred_fna_tgz_fp),
            'label': os.path.basename(pred_fna_tgz_fp),
            'description': 'FASTA-formatted nucleotide sequences of VIRSorter predicted phage'
        })

        pred_gb_tgz_fp = os.path.join(output_dir, 'VIRSorter_predicted_viral_gb.tar.gz')
        with tarfile.open(pred_gb_tgz_fp, 'w:gz') as pred_gb_tgz_fh:
            for pred_gb in pred_gbs:
                pred_gb_tgz_fh.add(pred_gb, arcname=os.path.basename(pred_gb))
        output_files.append({
            'path': pred_gb_tgz_fp,
            'name': os.path.basename(pred_gb_tgz_fp),
            'label': os.path.basename(pred_gb_tgz_fp),
            'description': 'Genbank-formatted sequences of VIRSorter predicted phage'
        })

        raw_html = self._parse_summary(glob_signal)
        html_fp = os.path.join(output_dir, 'index.html')

        with open(html_fp, 'w') as html_fh:
            html_fh.write(raw_html)

        report_shock_id = self.dfu.file_to_shock({
            'file_path': output_dir,
            'pack': 'zip'
        })['shock_id']

        html_report = [{
            'shock_id': report_shock_id,
            'name': os.path.basename(html_fp),
            'label': os.path.basename(html_fp),
            'description': 'HTML summary report for VIRSorter'
        }]

        report_params = {'message': 'Basic message to show in the report',
                         'workspace_name': params['workspace_name'],
                         'html_links': html_report,
                         'direct_html_link_index': 0,
                         'report_object_name': 'VIRSorter_report_{}'.format(str(uuid.uuid4())),
                         'file_links': output_files,
                         # Don't use until data objects that are created as result of running app
                         # 'objects_created': [{'ref': matrix_obj_ref,
                         #                      'description': 'Imported Matrix'}],
                         }

        kbase_report_client = KBaseReport(params['SDK_CALLBACK_URL'], token=params['KB_AUTH_TOKEN'])
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    def _mkdir_p(self, path):
        """
        :param path:
        :return:
        """

        if not path:
            return
        try:
            os.makedirs(path)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise
