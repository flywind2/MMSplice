import logging
from itertools import islice
from pkg_resources import resource_filename

import pandas as pd
import pyranges
from pybedtools import Interval
from kipoi.data import SampleIterator
from concise.preprocessing import encodeDNA
from kipoiseq.extractors import MultiSampleVCF
from mmsplice.utils import pyrange_remove_chr_from_chrom_annotation


logger = logging.getLogger('mmsplice')
logger.addHandler(logging.NullHandler())

GRCH37 = resource_filename('mmsplice', 'models/grch37_exons.csv.gz')
GRCH38 = resource_filename('mmsplice', 'models/grch38_exons.csv.gz')


def read_exon_pyranges(gtf_file, overhang=(100, 100), first_last=True):
    '''
    Read exon as pyranges from gtf_file

    Args:
      gtf_file: gtf file from ensembl/gencode.
      overhang: padding of exon to match variants.
      first_last: set overhang of first and last exon of the gene to zero
        so seq intergenic region will not be processed.
    '''
    df_gtf = pyranges.read_gtf(gtf_file).df
    df_exons = df_gtf[df_gtf['Feature'] == 'exon']
    df_exons = df_exons[['Chromosome', 'Start', 'End', 'Strand',
                         'exon_id', 'gene_id', 'gene_name', 'transcript_id']]

    if first_last:
        df_genes = df_gtf[df_gtf['Feature'] == 'transcript']
        df_genes.set_index('transcript_id', inplace=True)
        df_genes = df_genes.loc[df_exons['transcript_id']]
        df_genes.set_index(df_exons.index, inplace=True)

        starting = df_exons['Start'] == df_genes['Start']
        ending = df_exons['End'] == df_genes['End']

        df_exons.loc[:, 'left_overhang'] = ~starting * overhang[0]
        df_exons.loc[:, 'right_overhang'] = ~ending * overhang[1]

        df_exons.loc[:, 'Start'] -= df_exons['left_overhang']
        df_exons.loc[:, 'End'] += df_exons['right_overhang']

    return pyranges.PyRanges(df_exons)


def batch_iter_vcf(vcf_file, batch_size=10000):
    '''
    Iterates variatns in vcf file.

    Args:
      vcf_file: path of vcf file.
      batch_size: size of each batch.
    '''
    variants = MultiSampleVCF(vcf_file)
    batch = list(islice(variants, batch_size))

    while batch:
        yield batch
        batch = list(islice(variants, batch_size))


def variants_to_pyranges(variants):
    '''
    Create pyrange object given list of variant objects.

    Args:
      variants: list of variant objects have CHROM, POS, REF, ALT properties.
    '''
    def _from_variants(variants):
        for v in variants:
            if len(v.ALT) == 1:
                yield v.CHROM, v.POS, v.POS + max(len(v.REF), len(v.ALT[0])), v
            else:
                # Only support one alternative.
                # If multiple alternative, need to split into multiple variants
                logger.warning(
                    '%s has more than one or nan ALT sequence,'
                    'split into mutliple variants with bedtools' % v)

    df = pd.DataFrame(list(_from_variants(variants)),
                      columns=['Chromosome', 'Start', 'End', 'variant'])
    return pyranges.PyRanges(df)


def read_vcf_pyranges(vcf_file, batch_size=10000):
    '''
    Reads vcf and returns batch of pyranges objects.

    Args:
      vcf_file: path of vcf file.
      batch_size: size of each batch.
    '''
    for batch in batch_iter_vcf(vcf_file, batch_size):
        yield variants_to_pyranges(batch)


class SplicingVCFDataloader(SampleIterator):
    """
    Load genome annotation (gtf) file along with a vcf file,
      return wt sequence and mut sequence.

    Args:
        gtf: gtf file. Can be dowloaded from ensembl/gencode.
          Filter for protein coding genes.
        fasta_file: file path; Genome sequence
        vcf_file: vcf file, each line should contain one
          and only one variant, left-normalized
        spit_seq: whether or not already split the sequence
          when loading the data. Otherwise it can be done in the model class.
        endcode: if split sequence, should it be one-hot-encoded
    """

    def __init__(self, gtf, fasta_file, vcf_file,
                 variant_filter=True, split_seq=True, encode=True,
                 overhang=(100, 100), seq_spliter=None):

        self.gtf_file = gtf
        self.fasta_file = fasta_file
        self.vcf_file = vcf_file
        self.split_seq = split_seq
        self.encode = encode
        self.spliter = seq_spliter or SeqSpliter()

        self.pr_exons = self._read_exons(gtf, overhang)
        self.vseq_extractor = ExonSeqVcfSeqExtrator(fasta_file)
        self.fasta = self.vseq_extractor.fasta
        self.variants_batchs = read_vcf_pyranges(vcf_file)
        self.vcf = MultiSampleVCF(vcf_file)

        self._check_chrom_annotation()

        self._generator = self._generate(variant_filter=variant_filter)

    def _check_chrom_annotation(self):
        fasta_chroms = set(self.fasta.fasta.keys())
        vcf_chroms = set(self.vcf.seqnames)

        if not fasta_chroms.intersection(vcf_chroms):
            raise ValueError(
                'Fasta chrom names do not match with vcf chrom names')

        if self.gtf_file == 'grch37' or self.gtf_file == 'grch38':
            chr_annotaion = any(chrom.startswith('chr')
                                for chrom in vcf_chroms)
            if not chr_annotaion:
                self.pr_exons = pyrange_remove_chr_from_chrom_annotation(
                    self.pr_exons)

        gtf_chroms = set(self.pr_exons.Chromosome)
        if not gtf_chroms.intersection(vcf_chroms):
            raise ValueError(
                'GTF chrom names do not match with vcf chrom names')

    def _read_exons(self, gtf, overhang=(100, 100)):
        if gtf == 'grch37':
            if overhang != (100, 100):
                logger.warning('Overhang argument will be ignored'
                               ' for prebuild annotation.')
            return pyranges.PyRanges(pd.read_csv(GRCH37))
        elif gtf == 'grch38':
            if overhang != (100, 100):
                logger.warning('Overhang argument will be ignored'
                               ' for prebuild annotation.')
            return pyranges.PyRanges(pd.read_csv(GRCH38))
        else:
            return read_exon_pyranges(self.gtf_file, overhang=overhang)

    def _generate(self, variant_filter=True):
        for pr_variants in self.variants_batchs:

            exon_variant_pairs = pr_variants.join(
                self.pr_exons, suffix="_exon")

            for i, row in exon_variant_pairs.df.iterrows():
                yield row

    def __iter__(self):
        return self

    def __next__(self):
        row = next(self._generator)
        overhang = (row['left_overhang'], row['right_overhang'])
        exon = Interval(row['Chromosome'],
                        row['Start_exon'] + overhang[0] - 1,
                        row['End_exon'] - overhang[1],
                        strand=row['Strand'])
        variant = row['variant']

        seq = self.fasta.extract(Interval(
            exon.chrom, exon.start - overhang[0],
            exon.end + overhang[1], strand=exon.strand)).upper()
        mut_seq = self.vseq_extractor.extract(
            exon, [variant], overhang=overhang).upper()

        if exon.strand == '-':
            overhang = (overhang[1], overhang[0])

        if self.split_seq:
            seq = self.spliter.split(seq, overhang, exon)
            mut_seq = self.spliter.split(mut_seq, overhang, exon,
                                         pattern_warning=False)
            if self.encode:
                seq = self._encode_seq(seq)
                mut_seq = self._encode_seq(mut_seq)

        return {
            'inputs': {
                'seq': seq,
                'mut_seq': mut_seq
            },
            'metadata': {
                'variant': self._variant_to_dict(variant),
                'exon': self._exon_to_dict(row, exon, overhang)
            }
        }

    def batch_iter(self, batch_size=32):
        encode = self.encode
        self.encode = False

        for batch in super().batch_iter(batch_size):
            if encode:
                batch['inputs']['seq'] = self._encode_batch_seq(
                    batch['inputs']['seq'])
                batch['inputs']['mut_seq'] = self._encode_batch_seq(
                    batch['inputs']['mut_seq'])

            yield batch

        self.encode = encode

    def _encode_batch_seq(self, batch):
        return {k: encodeDNA(v.tolist()) for k, v in batch.items()}
