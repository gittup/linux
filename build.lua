compiled = {}

function obj_compile(obj)
	if(not compiled[obj]) then
		compiled[obj] = 1
		cfile = obj:sub(1, -3) .. ".[cS]"
		cc_linux(cfile)
		return obj
	end
	return nil
end

function process_y(obj)
	if(obj:find(".o", -2)) then
		local subvars = {}
		var_objs = obj:sub(1, -3) .. "-objs"
		var_y = obj:sub(1, -3) .. "-y"
		if(_G[var_objs]) then
			subvars += _G[var_objs]
		end
		if(_G[var_y]) then
			subvars += _G[var_y]
		end

		-- Make sure we don't have a thing like:
		-- file-mmu-y := file-mmu.o
		-- which would cause an infinite recursion here
		if(#subvars == 1 and subvars[1] == obj) then
			subvars = {}
		end

		if(#subvars > 0) then
			objlist = {}
			for k, v in ipairs(subvars) do
				objlist += process_y(v)
			end
			if(#objlist > 0) then
				ld_linux(objlist, obj)
			end
			return obj
		else
			return obj_compile(obj)
		end
	elseif(obj:find("/", -1)) then
		return obj .. "built-in.o"
	else
		print("Who knows: ", obj)
	end
end

obj_y = _G['obj-y']
local objs = {}
if(obj_y) then
	for k, v in ipairs(obj_y) do
		objs += process_y(v)
	end
end
ld_linux(objs, 'built-in.o')
