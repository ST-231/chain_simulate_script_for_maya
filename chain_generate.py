import pymel.core as pm
import maya.cmds as cmds
import math

try:
    import maya.app.mayabullet.RigidBody as RigidBody
    import maya.app.mayabullet.RigidBodyConstraint as RigidBodyConstraint
except ImportError:
    pm.error("无法导入 Maya Bullet 应用模块，请确认 Bullet 插件已正确安装和加载。")


def create_chain_links(curve_name, num_links=20, link_scale=1.0):
    """
    沿着一条曲线创建并正确摆放一系列链环几何体。
    """
    try:
        curve_node = pm.PyNode(curve_name)
    except pm.MayaNodeError:
        pm.error(f"找不到名为 '{curve_name}' 的曲线。")
        return None

    links = []
    chain_group = pm.group(empty=True, name="chain_grp")

    print(f"开始创建 {num_links} 个链环...")
    for i in range(num_links):
        param = float(i) / (num_links - 1)
   
        pos_list = cmds.pointOnCurve(curve_name, parameter=param, position=True)

        pos = pm.dt.Point(pos_list)
        
        link_transform = pm.polyTorus(radius=0.5 * link_scale, sectionRadius=0.1 * link_scale, name=f"link_{i}")[0]
        link_transform.setTranslation(pos)

        tangent_list = cmds.pointOnCurve(curve_name, parameter=param, normalizedTangent=True)
        tangent = pm.dt.Vector(tangent_list)

        target_loc = pm.spaceLocator()
        target_loc.setTranslation(pos + tangent)
        
        aim_const = pm.aimConstraint(target_loc, link_transform, aimVector=(0, 0, 1), upVector=(0, 1, 0))
        
        pm.delete(aim_const, target_loc)
        
        if i % 2 == 1:
            pm.rotate(link_transform, [0, 90, 0], relative=True, objectSpace=True)
            
        pm.parent(link_transform, chain_group)
        links.append(link_transform)

    print("链环几何体创建完毕。")
    return chain_group

def convert_links_to_rigid_bodies(piece_group):
    pieces = piece_group.getChildren(type='transform')
    print(f"开始将 {len(pieces)} 个链环转换为刚体...")
    for piece in pieces:
        pm.select(piece)
        result_nodes = RigidBody.CreateRigidBody(True).executeCommandCB()
        if result_nodes and len(result_nodes) > 1:
            rb_shape = pm.PyNode(result_nodes[1])
            rb_shape.colliderShapeType.set(3)
    print("所有链环已成功转换为刚体。")

def connect_chain_links(piece_group):
    all_links = piece_group.getChildren(type='transform')
    pieces = sorted(all_links, key=lambda node: int(node.name().split('_')[-1]))
    
    num_pieces = len(pieces)
    print(f"开始为 {num_pieces} 个刚体生成约束...")
    for i in range(num_pieces - 1):
        piece_a, piece_b = pieces[i], pieces[i+1]
        pm.select(piece_a, piece_b)
        RigidBodyConstraint.CreateRigidBodyConstraint().executeCommandCB()
    print("链条约束连接完毕。")

def create_physical_chain(curve_name, num_links=20, link_scale=1.0):
    """
    执行创建物理链条的完整流程。
    """
    if not pm.pluginInfo("bullet.mll", query=True, loaded=True):
        pm.loadPlugin("bullet.mll")

    # Phase 1: 创建链环几何体
    chain_group = create_chain_links(curve_name, num_links, link_scale)
    
    if chain_group and chain_group.getChildren():
        # Phase 2: 将链环转换为刚体
        convert_links_to_rigid_bodies(chain_group)
        
        # Phase 3: 连接链环
        connect_chain_links(chain_group)
        
        print("\n--- 物理链条已生成！---")
        all_links = chain_group.getChildren(type='transform')
        sorted_links = sorted(all_links, key=lambda node: int(node.name().split('_')[-1]))
        first_link = sorted_links[0]
     
        first_link_rb_shape = first_link.getShape().connections(type='bulletRigidBodyShape')[0]
        first_link_rb_shape.bodyType.set(1)
        print(f"提示: '{first_link.name()}' 已被设置为运动学刚体（固定点）。")

    else:
        print("创建链环失败。")


# --- 执行脚本 ---
create_physical_chain('curve1', num_links=25, link_scale=0.8)