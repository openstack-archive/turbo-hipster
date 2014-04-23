// Copyright 2014 Rackspace Australia
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

(function ($) {
    $container = $('#report_container');
    source = 'jjb_report.json';
    detailed = location.search.match(/[?&]detailed=([^?&]*)/);

    function get_stats(data) {
        $stats = $('<div>');
        if ('_jobs' in data) {
            num_jobs = data['_jobs'].length
            $jobs = $('<p>')
                .html(num_jobs + ' jobs have this item');

            if (detailed && (detailed[1] == 'true' || detailed[1] == 'jobs')) {
                $job_list = $('<ul>')
                    .css('display', 'none');

                for (job in data['_jobs']) {
                    $job_item = $('<li>')
                        .html(data['_jobs'][job]);
                    $job_list.append($job_item);
                }
                $jobs.append($job_list);
                $jobs.css('cursor', 'pointer')
                    .click(function() {
                        $(this).children().toggle();
                    });
            }

            $stats.append($jobs);
        }

        if ('_values' in data) {
            num_values = Object.keys(data['_values']).length
            $value_header = $('<p>')
                .html(num_values + ' jobs have values');
            $values = $('<div>')
                .append($value_header);

            if (detailed &&
                (detailed[1] == 'true' || detailed[1] == 'values')) {
                $job_list = $('<ul>')
                    .css('display', 'none');

                for (job in data['_values']) {
                    $values_list = $('<ul>')
                    for (value in data['_values'][job]) {

                        $value_item = $('<li>')
                            .html(data['_values'][job][value]);
                        $values_list.append($value_item);
                    }
                    $job_item = $('<li>')
                        .append($('<p>').html(job), $values_list);
                    $job_list.append($job_item);
                }
                $values.append($job_list);
                $value_header.css('cursor', 'pointer')
                    .click(function() {
                        $(this).next().toggle();
                    });
            }
            $stats.append($values);
        }
        return $stats;
    }

    function get_progress(data) {
        $bar_outter = $('<div />')
            .addClass('progress');

        total_supported = 0;
        total_ignored = 0;
        total_unsupported = 0;

        for (sub in data) {
            if (sub.substring(0, 1) !== '_') {
                if (data[sub]['_support'] == 'supported') {
                    total_supported += data[sub]['_jobs'].length
                }
                else if (data[sub]['_support'] == 'ignored') {
                    total_ignored += data[sub]['_jobs'].length
                }
                else {
                    total_unsupported += data[sub]['_jobs'].length
                }
            }
        }

        overall_total = total_supported + total_unsupported + total_ignored;

        $bar_inner = $('<div />')
            .addClass('progress-bar')
            .addClass('progress-bar-success')
            .css('width', (100 * total_supported/overall_total) + '%');
        $bar_outter.append($bar_inner);

        $bar_inner = $('<div />')
            .addClass('progress-bar')
            .addClass('progress-bar-warning')
            .css('width', (100 * total_ignored/overall_total) + '%');
        $bar_outter.append($bar_inner);

        $bar_inner = $('<div />')
            .addClass('progress-bar')
            .addClass('progress-bar-danger')
            .css('width', (100 * total_unsupported/overall_total) + '%');
        $bar_outter.append($bar_inner);

        return $bar_outter;
    }

    function handle_data(data, $node) {
        for (var key in data) {
            if (key.substring(0, 1) !== '_') {

                $panel_heading = $('<div>')
                    .addClass('panel-heading')
                    .html(key);

                sub_items = Object.keys(data[key]).length - 1;
                if ('_jobs' in data[key]){
                    sub_items -= 1;
                }
                if ('_values' in data[key]){
                    sub_items -= 1;
                }
                if (sub_items > 0 ) {
                    $progress = get_progress(data[key]);
                    $panel_heading.append($progress);
                }

                $panel_heading.css('cursor', 'pointer')
                    .click(function() {
                        $(this).next().toggle();
                    });

                if ('_support' in data) {
                    if (data[key]['_support'] == 'supported') {
                        $panel_heading.addClass('bg-success')
                            .css('background-color', 'rgb(223, 240, 216)');
                    }
                    else if (data[key]['_support'] == 'ignored') {
                        $panel_heading.addClass('bg-warning')
                            .css('background-color', 'rgb(252, 248, 227)');
                    }
                    else {
                        $panel_heading.addClass('bg-danger')
                            .css('background-color', 'rgb(242, 222, 222)');
                    }
                }

                $stats = get_stats(data[key]);

                $panel_body = $('<div>')
                    .addClass('panel-body')
                    .css('display', 'none')
                    .append($stats);

                $panel = $('<div>')
                    .addClass('panel')
                    .addClass('panel-default')
                    .append($panel_heading, $panel_body);

                $node.append($panel);

                handle_data(data[key], $panel_body);
            }
        }
    }

    $.getJSON(source).done(function (data) {
        handle_data(data['functions'], $container);
    });

}(jQuery));
