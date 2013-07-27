import bpy
from bpy_extras.io_utils import ExportHelper
from mathutils import *
from math import *
import struct

"""
MDL file format export

HEADER:
    3 byte: magic number (MDL)
    1 byte: version number (2)
    4 byte: number of verts
    4 bytea: number of faces
    1 byte: number of bones
    16 byte: name
    3 byte: padding
    32

VERT:
    12 byte: position (3 * 4 byte float)
    6 byte: normal (3 * 2 byte signed short) (normalized from -32768 to 32767)
    4 byte: uv coordinate (2 * 2 byte) (normalized from 0 to 65535)
    2 byte: material
    1 byte: boneID 1
    1 byte: boneID 2
    1 byte: bone weight 1
    1 byte: bone weight 2
    4 byte: padding         #TODO lighting properties
    32

FACE:
    6 byte: vertex indices
    6

MDL:
    HEADER,
    VERTS,
    FACES
"""

def float_to_ushort(val):
    if val >= 1.0:
        return 2**16-1
    if val <= 0.0:
        return 0
    return int(floor(val * (2**16-1)))

def float_to_short(val):
    if val >= 1.0:
        return 2**15-1
    if val <= -1.0:
        return -(2**15)+1
    return int(round(val * (2**15-1)))

def float_to_ubyte(val):
    if val >= 1.0:
        return 2**8-1
    if val <= 0.0:
        return 0
    return int(round(val * (2**8-1)))

def vec2_to_uhvec2(val):
    return tuple((float_to_ushort(val[0]), float_to_ushort(val[1])))

def vec3_to_hvec3(val):
    return tuple((float_to_short(val[0]), float_to_short(val[1]), float_to_short(val[2])))

def uv_entry_tuple(mesh, facei, uvi):
    face = mesh.tessfaces[facei]
    uv_raw = (0.0, 0.0)
    if mesh.tessface_uv_textures.active:
        uvface = mesh.tessface_uv_textures.active.data[facei]
        uv_raw = (uvface.uv_raw[uvi * 2], uvface.uv_raw[uvi * 2 + 1])
    uv = vec2_to_uhvec2(uv_raw)
    entry = (face.vertices[uvi], uv[0], uv[1])
    return entry

def vert_list_entry_id(mesh, vert_list, entry):
    if(entry not in vert_list):
        vert_list.append(entry)
    return vert_list.index(entry)

def get_face_list(mesh, vert_list):
    lst = list()
    for i in range(len(mesh.tessfaces)):
        faceverts = list()
        for j in range(3):
            entry = uv_entry_tuple(mesh, i, j)
            faceverts.append(vert_list_entry_id(mesh, vert_list, entry))
        lst.append(faceverts)
    return lst

def bone_weight_normalize(bones):
    BONEW1 = 2; BONEW2 = 3
    b_sum = bones[BONEW1] + bones[BONEW2]
    if b_sum > 0:
        bones[BONEW1] = float_to_ubyte(bones[BONEW1] / b_sum)
        bones[BONEW2] = float_to_ubyte(bones[BONEW2] / b_sum)
    else:
        bones[BONEW1] = 0
        bones[BONEW2] = 0
    return bones

def bone_id_of_group(obj, groupid, blist):
    BONE = 3
    nm = obj.vertex_groups[groupid].name
    for i in range(0, len(blist)):
        if(nm == blist[i][BONE].name):
            print(nm + " is group " + str(i));
            return i
    return None

def vert_get_bones(obj, vert, blist):
    boneid = [255, 255]
    bonew = [0.0, 0.0]
    for group in vert.groups:
        g_boneid = bone_id_of_group(obj, group.group, blist)
        if g_boneid != None:
            if group.weight > bonew[0]:
                bonew[1] = bonew[0]
                boneid[1] = boneid[0]
                bonew[0] = group.weight
                boneid[0] = g_boneid
            elif group.weight > bonew[1]:
                bonew[1] = group.weight
                boneid[1] = g_boneid
    return bone_weight_normalize([boneid[0], boneid[1], bonew[0], bonew[1]])

def find_bone_parentid(arm, bone):
    if(bone.parent):
        for i in range(len(arm.data.bones)):
            if(arm.data.bones[i] == bone.parent):
                return i
    return 255

def get_bone_list(obj):
    armature = obj.find_armature()
    blist = []
    if(armature):
        for i in range(0, len(armature.data.bones)):
            bone = armature.data.bones[i]
            pid = find_bone_parentid(armature, bone)
            blist.append([bone.name, i, pid, bone])
    return blist

def write_mdl_header(file, obj, vlist, flist, blist):
    hfmt = "3sBIIB15sxxxx"

    header = struct.pack(hfmt, b"MDL", 4,
                len(vlist),
                len(flist),
                len(blist),#number of bones
                bytes(obj.data.name, "UTF-8"))
    file.write(header)

def write_mdl_verts(file, obj, vlist, blist):
    tmat = Matrix.Rotation(-pi/2.0, 3, Vector((1,0,0))) #turns verts right side up (+y)
    VERTID = 0; UV1 = 1; UV2 = 2
    BONEID1 = 0; BONEID2 = 1; BONEW1 = 2; BONEW2 = 3
    vfmt = "fffhhhHHHBBBBxxxx"
    for vert in vlist:
        co = tmat * obj.data.vertices[vert[VERTID]].co
        norm = vec3_to_hvec3(tmat * obj.data.vertices[vert[VERTID]].normal)
        uv = tuple((vert[UV1], vert[UV2]))
        bones = vert_get_bones(obj, obj.data.vertices[vert[VERTID]], blist)

        vbits = struct.pack(vfmt, co[0], co[1], co[2],
                            norm[0], norm[1], norm[2],
                            uv[0], uv[1],
                            0, #material ID
                            bones[BONEID1], bones[BONEID2], #bone IDs
                            bones[BONEW1], bones[BONEW2]) #bone weights
        file.write(vbits)

def write_mdl_faces(file, mesh, flist):
        ffmt = 'HHH'
        for face in flist:
            fbits = struct.pack(ffmt, face[0], face[1], face[2])
            file.write(fbits)

def write_mdl_mesh(context, filepath, settings):
    if not context.object.type == "MESH":
            raise Exception("Mesh must be selected, " + context.object.type + " was given")

    obj = context.object
    mesh = obj.data
    mesh.update(calc_tessface=True)
    if not is_trimesh(mesh):
        raise Exception ("Mesh is not triangulated")

    vlist = list()
    flist = get_face_list(mesh, vlist) #modifies vlist (i know... bad)
    blist = get_bone_list(obj)

    f = open(filepath, 'wb')
    write_mdl_header(f, obj, vlist, flist, blist)
    write_mdl_verts(f, obj, vlist, blist)
    write_mdl_faces(f, mesh, flist)
    f.close()
    return {'FINISHED'}

def is_trimesh(mesh):
    ret = True
    for face in mesh.tessfaces:
        if len(face.vertices) > 3:
            ret = False
            break
    return ret

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

class MdlExport(Operator, ExportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "export.mdl"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Export Custom Model"

    # ExportHelper mixin class uses this
    filename_ext = ".mdl"

    filter_glob = StringProperty(
            default="*.mdl",
            options={'HIDDEN'},
            )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    """
    use_setting = BoolProperty(
           name="Example Boolean",
            description="Example Tooltip",
            default=True,
            )

    type = EnumProperty(
            name="Example Enum",
            description="Choose between two items",
            items=(('OPT_A', "First Option", "Description one"),
                   ('OPT_B', "Second Option", "Description two")),
            default='OPT_A',
            )
    """

    def execute(self, context):
        return write_mdl_mesh(context, self.filepath, None)


# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(MdlExport.bl_idname, text="Custom Model (.mdl)")


def register():
    bpy.utils.register_class(MdlExport)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(MdlExport)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()

    # test call
    bpy.ops.export.mdl('INVOKE_DEFAULT')