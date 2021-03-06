/*
A KBase module: VirSorter
*/

module VirSorter {

    typedef string obj_ref;

    typedef structure {
        string report_name;
        string report_ref;
        string workspace_name;
        obj_ref genomes;
        string database;
        obj_ref add_genomes;
        string virome;
        string diamond;
        string keep_db;
        string no_c;
        string binned_contig_name;

    } InParams;

    /*
        result_folder: folder path that holds all files generated by VIRSorter
        report_name: report name generated by KBaseReport
        report_ref: report reference generated by KBaseReport
    */
    typedef structure{
        obj_ref binned_contig_obj_ref;
        string result_directory;
        string report_name;
        string report_ref;
    }VirSorterResult;

    funcdef run_VirSorter(InParams params)
        returns (VirSorterResult returnVal) authentication required;

};
