#!/usr/bin/python
# This tool is useful to query gerrit for negative or missing votes left by
# a user. It may require tweaking for different failure messages etc.

import json
import requests
import traceback

# Set the user to watch
user = 'turbo-hipster'

# Grab a list of missing or negative reviews for a user:
url = ("https://review.openstack.org/changes/?q=status:open "
       "project:openstack/nova NOT label:Verified>=0,%s "
       "branch:master&o=CURRENT_REVISION&o=MESSAGES" % user)

print "Grabbing reviews from %s" % url
r = requests.get(url)

no_votes = []
negative_votes = []
merge_failures = []
unknown = []

for change in json.loads(r.text[5:]):
    try:
        patchset = change['revisions'][change['current_revision']]['_number']
        change_id = str(change['_number']) + ',' + str(patchset)
        last_message = None
        for message in sorted(change['messages'],
                              key=lambda k: (k['_revision_number'],
                                             k['date']), reverse=True):
            if message['_revision_number'] < patchset:
                # Finished looking at all the messages on this patchset
                break
            if message['author']['name'] == user:
                last_message = message['message']
                break

        if not last_message:
            # turbo-hister hasn't commented on this patchset
            no_votes.append({
                'change_id': change_id,
                'updated': change['updated'],
                'change': change
            })
        elif ('This change was unable to be automatically merged with the '
              'current state of the repository.' in last_message):
            merge_failures.append({
                'change_id': change_id,
                'updated': change['updated'],
                'change': change
            })
        elif 'Database migration testing failed' in last_message:
            negative_votes.append({
                'change_id': change_id,
                'updated': change['updated'],
                'change': change
            })
        else:
            unknown.append({
                'change_id': change_id,
                'updated': change['updated'],
                'change': change
            })

    except Exception:
        print "Something failed.. Here is the change..."
        print change
        traceback.print_exc()


def print_enqueues(changes):
    for change in sorted(changes, key=lambda k: k['updated'], reverse=True):
        print ("zuul enqueue --trigger gerrit --pipeline check "
               "--project openstack/nova --change %s" % (change['change_id']))

print "="*20 + (" Changes with no votes (%d) " % len(no_votes)) + "="*20
print_enqueues(no_votes)
print ("="*20 + (" Changes with negative votes (%d) " % len(negative_votes)) +
       "="*20)
print_enqueues(negative_votes)
print ("="*20 + (" Changes with merge failure (%d) " % len(merge_failures)) +
       "="*20)
print_enqueues(merge_failures)
print "="*20 + (" Others in this query (%d) " % len(unknown)) + "="*20
print_enqueues(unknown)
