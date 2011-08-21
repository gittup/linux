#! /bin/sh -e
files=`for i in $@; do echo $i; done | sort | uniq`
for i in $files; do
	base=`basename $i .o`
	if [ -f $base.c ]; then
		echo ": $base.c |> !cc_linux |>"
	elif [ -f $base.S ]; then
		echo ": $base.S |> !cc_linux |>"
	else
		echo "$0 Error: Base file for '$i' not found." 1>&2
		exit 1
	fi
done
echo ": $@ |> !ar |> lib.a"
