LINUX_ROOT = tup.getcwd()

function cc_linux(file)
	inputs = {file}
	inputs.extra_inputs += '$(GITTUP_ROOT)/<compiler_files>'
	CC = LINUX_ROOT .. '/../gcc/gcc/xgcc -B' .. LINUX_ROOT .. '/../gcc/gcc -B' .. LINUX_ROOT .. '/../binutils/gas'
	tup.foreach_rule(inputs, '^ CC %f^ $(CC) -c %f -o %o $(CFLAGS) $(CFLAGS_%e) $(CFLAGS_%f) -D"KBUILD_STR(s)=#s" -D"KBUILD_BASENAME=KBUILD_STR(%B)" -D"KBUILD_MODNAME=KBUILD_STR(%B)"', '%B.o')
end

function ld_linux(objlist, obj)
	if(#objlist > 0) then
		objlist.extra_inputs += '$(GITTUP_ROOT)/<compiler_files>'
		tup.rule(objlist, '^ LD %o^ $(LINUX_ROOT)/../binutils/ld/ld -m elf_i386 -r -o %o %f ', obj)
	else
		tup.rule({}, '^ EMPTY %o^ ar crs %o', obj)
	end
end

--!ld_linux = | $(link-y) $(LD) |> ^ LD %o^ $(LD) -m elf_i386 -r -o %o %f $(link-y) |>
--!ld_linux.EMPTY = |> ^ EMPTY %o^ ar crs %o |>
