# Copyright ...

""" Methods to handle the results of the task.

Primarily place the log files somewhere useful and optionally email
somebody """

def push_file(local_file):
    """ Push a log file to a server. Returns the public URL """
    pass

def generate_log_index(logfiles):
    """ Create an index of logfiles and links to them """
    # Loop over logfile URLs
    # Create summary and links

def make_index_file(logfiles):
    """ Writes an index into a file for pushing """
    generate_log_index(logfiles)
    # write out to file

def generate_push_results(logfiles):
    """ Generates and pushes results """
    for logfile in logfiles:
        push_file(logfile)

    index_file = make_index_file()
    index_file_url = push_file(index_file)

    return index_file_url