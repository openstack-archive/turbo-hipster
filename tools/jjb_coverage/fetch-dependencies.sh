#!/bin/bash
BASE_DIR=$(cd $(dirname $0); pwd)
echo "Destination: $BASE_DIR/public_html"

echo "Fetching jquery.min.js..."
curl --silent http://code.jquery.com/jquery.min.js > $BASE_DIR/public_html/jquery.min.js

echo "Fetching jquery-visibility.min.js..."
curl --silent https://raw.github.com/mathiasbynens/jquery-visibility/master/jquery-visibility.min.js > $BASE_DIR/public_html/jquery-visibility.min.js

echo "Fetching bootstrap..."
curl -L --silent https://github.com/twbs/bootstrap/releases/download/v3.1.1/bootstrap-3.1.1-dist.zip > bootstrap.zip
unzip -q -o bootstrap.zip -d $BASE_DIR/public_html/
mv $BASE_DIR/public_html/bootstrap-3.1.1-dist $BASE_DIR/public_html/bootstrap
rm bootstrap.zip
