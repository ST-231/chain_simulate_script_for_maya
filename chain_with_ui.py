# ===================================================================
# 物理链条生成器
# ===================================================================
import pymel.core as pm
import maya.cmds as cmds
import maya.app.mayabullet.RigidBody as RigidBody
import maya.app.mayabullet.RigidBodyConstraint as RigidBodyConstraint
import math
import random

class ChainGeneratorUI:
    def __init__(self):
        """初始化窗口"""
        self.window_name = "chainGeneratorWindow"
        self.window_title = "物理链条生成器"
        if pm.window(self.window_name, exists=True):
            pm.deleteUI(self.window_name)

    def create_ui(self):
        """创建UI窗口和所有控件"""
        with pm.window(self.window_name, title=self.window_title, widthHeight=(350, 220)) as self.window:
            with pm.columnLayout(adjustableColumn=True, rowSpacing=5, margins=10):
                pm.text(label="1. 参数设置", align='left', font='boldLabelFont')
                self.curve_textfield = pm.textFieldButtonGrp(
                    label="驱动曲线:", 
                    buttonLabel="拾取选择", 
                    cw3=[70, 180, 60],
                    buttonCommand=self.on_pick_curve_button_click
                )
                self.num_links_slider = pm.intSliderGrp(field=True, label="链环数量:", minValue=3, maxValue=100, value=25, cw3=[70, 60, 50])
                
                pm.separator(height=10, style='in')
                pm.text(label="2. 固定模式", align='left', font='boldLabelFont')
                self.fixing_mode_radio = pm.radioButtonGrp(
                    label="模式:",
                    labelArray3=['固定首端', '固定末端', '固定两端'],
                    numberOfRadioButtons=3,
                    select=1,
                    cw4=[70, 80, 80, 80]
                )
                
                pm.separator(height=15, style='in')
                pm.button(label="生成物理链条", height=40, command=self.on_create_button_click)

        self.window.show()

    def on_pick_curve_button_click(self, *args):
        selection = pm.ls(selection=True, type='transform')
        if selection and selection[0].getShape(type='nurbsCurve'):
            self.curve_textfield.setText(selection[0].name())
        else:
            pm.warning("请先选择一条NURBS曲线！")

    def on_create_button_click(self, *args):
        curve_name = self.curve_textfield.getText()
        if not pm.objExists(curve_name):
            pm.error(f"找不到名为 '{curve_name}' 的曲线。")
            return
            
        num_links = self.num_links_slider.getValue()
        link_scale = 0.8
        fixing_mode = self.fixing_mode_radio.getSelect()

        # 调用主逻辑
        chain_group = self._create_natural_chain(curve_name, num_links, link_scale)
        if not chain_group:
            pm.error("链条创建失败！")
            return

        all_links = sorted(chain_group.getChildren(type='transform'), key=lambda node: 'constraint' not in node.name())
        all_links = sorted(all_links, key=lambda node: int(node.name().split('_')[-1]))
        
        if not all_links:
            return
        
        # 创建一个专门存放控制器的组，并放入主链条组下
        controls_group = pm.group(empty=True, name="controls_grp", parent=chain_group)

        if fixing_mode == 1: # 固定首端
            self._create_controller_for_link(all_links[0], controls_group)
        elif fixing_mode == 2: # 固定末端
            self._create_controller_for_link(all_links[-1], controls_group)
        elif fixing_mode == 3: # 固定两端
            self._create_controller_for_link(all_links[0], controls_group)
            self._create_controller_for_link(all_links[-1], controls_group)
            
        pm.select(chain_group)
        print("链条和控制器已生成！请选择控制器进行动画。")

        def set_link_kinematic(link_node):
            try:
                rb_shape = link_node.getShape().connections(type='bulletRigidBodyShape')[0]
                rb_shape.bodyType.set(1)
                print(f"'{link_node.name()}' 已设置为固定点。")
            except IndexError:
                pm.warning(f"无法为'{link_node.name()}'找到bullet刚体形状。")

        if fixing_mode == 1:
            set_link_kinematic(all_links[0])
        elif fixing_mode == 2:
            set_link_kinematic(all_links[-1])
        elif fixing_mode == 3:
            set_link_kinematic(all_links[0])
            set_link_kinematic(all_links[-1])
            
        pm.select(chain_group)
        print("链条生成完毕！现在可以播放动画并移动固定点进行交互。")

    # ===================================================================
    # 核心逻辑方法 (从原始脚本迁移而来)
    # ===================================================================

    def _create_natural_chain(self, curve_name, num_links, link_scale):
        # 定义与曲线绑定的链条组名称
        chain_group_name = f"chain_grp_{curve_name}"

        # 检查并只删除与此曲线相关的旧链条组
        if pm.objExists(chain_group_name):
            print(f"找到已存在的链条 '{chain_group_name}'，将进行清理...")
            pm.delete(chain_group_name)
        
        # 同时删除求解器防止崩溃
        if pm.objExists('bulletSolverShape1'):
            solver_transform = pm.PyNode('bulletSolverShape1').getParent()
            print(f"清理旧的Bullet求解器: {solver_transform.name()}")
            pm.delete(solver_transform)
        
        if not pm.pluginInfo("bullet.mll", query=True, loaded=True):
            pm.loadPlugin("bullet.mll")
        
        print("=" * 50)
        print("开始创建自然交替的物理链条...")
        
        # 调用创建函数
        chain_group = self._create_chain_links(curve_name, num_links, link_scale)
        
        if chain_group and chain_group.getChildren():
            # 重命名组
            chain_group.rename(chain_group_name)

            self._convert_links_to_rigid_bodies(chain_group)
            self._setup_simulation_environment()
            self._connect_chain_links(chain_group, link_scale)
            print("自然物理链条核心部分已生成！")
            return chain_group
        else:
            print("创建链环失败，流程中止。")
            return None

    def _create_chain_links(self, curve_name, num_links, link_scale):
        """创建交替嵌套的链环几何体"""
        try:
            curve_node = pm.PyNode(curve_name)
        except pm.MayaNodeError:
            pm.error(f"找不到名为 '{curve_name}' 的曲线。")
            return None
        
        links = []
        chain_group = pm.group(empty=True, name="chain_grp")
        print(f"开始创建 {num_links} 个交替嵌套的链环...")
        
        # 获取曲线总长度
        curve_length = cmds.arclen(curve_name)
        
        # 动态计算链环间距，确保嵌套
        link_diameter = 0.6 * link_scale  # 链环直径
        ideal_spacing = link_diameter * 0.7  # 理想间距为直径的70%
        
        # 如果曲线太长，压缩间距；如果太短，拉伸曲线概念上的使用
        total_needed_length = ideal_spacing * (num_links - 1)
        spacing_factor = min(1.0, curve_length / total_needed_length) if total_needed_length > 0 else 1.0
        
        print(f"链环直径: {link_diameter:.3f}, 理想间距: {ideal_spacing:.3f}")
        print(f"曲线长度: {curve_length:.3f}, 间距系数: {spacing_factor:.3f}")
        
        for i in range(num_links):
            if num_links > 1:
                param = float(i) / (num_links - 1)
            else:
                param = 0
            
            pos_list = cmds.pointOnCurve(curve_name, parameter=param, position=True)
            pos = pm.dt.Point(pos_list)
            
            # 创建链环
            main_radius = 0.3 * link_scale
            tube_radius = 0.06 * link_scale
            
            link_transform = pm.polyTorus(
                radius=main_radius,
                sectionRadius=tube_radius,
                subdivisionsAxis=16,
                subdivisionsHeight=8,
                name=f"link_{i:02d}"
            )[0]
            
            link_transform.setTranslation(pos)
            
            # 获取曲线切线方向
            tangent_list = cmds.pointOnCurve(curve_name, parameter=param, normalizedTangent=True)
            tangent = pm.dt.Vector(tangent_list)
            
            # 计算正确的交替朝向
            if i == 0:
                # 第一个链环：建立稳定的基准朝向
                forward = tangent.normal()
                world_up = pm.dt.Vector(0, 1, 0)
                right = forward.cross(world_up).normal()
                if right.length() < 0.1:
                    right = pm.dt.Vector(1, 0, 0).cross(forward).normal()
                up = right.cross(forward).normal()
                
            elif i == 1:
                # 第二个链环：直接垂直于第一个
                prev_matrix = links[0].getMatrix(worldSpace=True)
                prev_forward = pm.dt.Vector(prev_matrix[2][:3])
                prev_right = pm.dt.Vector(prev_matrix[0][:3])
                
                forward = prev_right.normal()  # 90度旋转
                world_up = pm.dt.Vector(0, 1, 0)
                up = world_up - forward * (world_up.dot(forward))
                up = up.normal()
                right = forward.cross(up).normal()
                
            else:
                # 后续链环都基于前一个链环
                prev_matrix = links[i-1].getMatrix(worldSpace=True)
                prev_forward = pm.dt.Vector(prev_matrix[2][:3])
                prev_right = pm.dt.Vector(prev_matrix[0][:3])
                prev_up = pm.dt.Vector(prev_matrix[1][:3])
                
                # 简化的交替逻辑
                if i % 2 == 1:
                    forward = prev_right.normal()
                else:
                    forward = prev_up.normal()
                
                # 保持合理的up方向
                world_up = pm.dt.Vector(0, 1, 0)
                up = world_up - forward * (world_up.dot(forward))
                if up.length() < 0.1:
                    up = tangent.cross(forward).normal()
                up = up.normal()
                right = forward.cross(up).normal()
            
            # 验证向量的正交性和有效性
            if forward.length() < 0.01 or up.length() < 0.01 or right.length() < 0.01:
                print(f"警告：链环 {i} 的方向向量异常，使用默认方向")
                forward = tangent.normal()
                up = pm.dt.Vector(0, 1, 0)
                right = forward.cross(up).normal()
                if right.length() < 0.01:
                    right = pm.dt.Vector(1, 0, 0)
                up = right.cross(forward).normal()
            
            # 确保向量单位化
            forward = forward.normal()
            up = up.normal()
            right = right.normal()
            
            # 构建变换矩阵
            matrix = [
                right.x, right.y, right.z, 0,
                up.x, up.y, up.z, 0,
                forward.x, forward.y, forward.z, 0,
                pos.x, pos.y, pos.z, 1
            ]
            
            # 应用变换矩阵
            transform_matrix = pm.dt.Matrix(matrix)
            link_transform.setMatrix(transform_matrix, worldSpace=True)
      
            # 对于前几个链环，减少随机扰动以避免抖动
            if i < 8:
                small_rotation = [
                    (random.random() - 0.5) * 1,
                    (random.random() - 0.5) * 1,
                    (random.random() - 0.5) * 1
                ]
            else:
                small_rotation = [
                    (random.random() - 0.5) * 2,
                    (random.random() - 0.5) * 2,
                    (random.random() - 0.5) * 2
                ]
            
            pm.parent(link_transform, chain_group)
            links.append(link_transform)
            
            print(f"创建链环 {i+1}/{num_links}: {link_transform.name()}")
        
        print("交替嵌套链环几何体创建完毕。")
        return chain_group

    def _convert_links_to_rigid_bodies(self, piece_group):
        """转换为刚体，优化物理属性"""
        pieces = piece_group.getChildren(type='transform')
        print(f"开始将 {len(pieces)} 个链环转换为刚体...")
        
        for i, piece in enumerate(pieces):
            pm.select(piece)
            result_nodes = RigidBody.CreateRigidBody(True).executeCommandCB()
            
            if result_nodes and len(result_nodes) > 1:
                rb_shape = pm.PyNode(result_nodes[1])
                
                # 使用网格碰撞形状以获得更准确的碰撞
                rb_shape.colliderShapeType.set(2)  # 网格形状
                
                # 优化物理属性
                rb_shape.mass.set(0.05)  # 更轻的质量
                rb_shape.linearDamping.set(0.3)
                rb_shape.angularDamping.set(0.4)
                
                # 调整材质属性
                rb_shape.friction.set(0.4)
                rb_shape.restitution.set(0.05)  # 很低的弹性
                
                print(f"链环 {piece.name()} 已转换为刚体")
        
        print("所有链环已成功转换为刚体。")

    def _connect_chain_links(self, piece_group, link_scale=1.0):
        """创建更精确的链环约束连接"""
        all_links = piece_group.getChildren(type='transform')
        pieces = sorted(all_links, key=lambda node: int(node.name().split('_')[-1]))
        
        num_pieces = len(pieces)
        print(f"开始为 {num_pieces} 个刚体生成精确约束...")
    
        for i in range(num_pieces - 1):
            piece_a, piece_b = pieces[i], pieces[i+1]
            
            # 获取链环位置
            pos_a = piece_a.getTranslation(space='world')
            pos_b = piece_b.getTranslation(space='world')
            
            # 计算连接点 - 应该在两个链环的接触面上
            direction = (pos_b - pos_a).normal()
            
            # 链环半径
            link_radius = 0.3 * link_scale
            
            # 计算更精确的连接点
            # 对于交替的链环，连接点在环的侧面
            link_a_matrix = piece_a.getMatrix(worldSpace=True)
            link_b_matrix = piece_b.getMatrix(worldSpace=True)
            
            # 获取链环A的前向和右向
            a_forward = pm.dt.Vector(link_a_matrix[2][:3])
            a_right = pm.dt.Vector(link_a_matrix[0][:3])
            
            # 获取链环B的前向和右向
            b_forward = pm.dt.Vector(link_b_matrix[2][:3])
            b_right = pm.dt.Vector(link_b_matrix[0][:3])
            
            # 对于垂直相交的链环，连接点在它们的相交区域
            center_point = (pos_a + pos_b) / 2.0
            
            # 调整连接点位置，更靠近实际的接触点
            offset_a = direction * link_radius * 0.3
            offset_b = -direction * link_radius * 0.3
            
            connection_point = center_point
            
            # 创建约束
            pm.select(piece_a, piece_b)
            new_nodes = RigidBodyConstraint.CreateRigidBodyConstraint().executeCommandCB()
    
            if new_nodes:
                constraint_shape = pm.PyNode(new_nodes[0])
                constraint_transform = constraint_shape.getParent()
                
                constraint_transform.rename(f"constraint_{piece_a.name()}_{piece_b.name()}")
                # 将约束节点作为子级放入主链条组中
                pm.parent(constraint_transform, piece_group)
                
                # 设置为链条约束（更适合链条连接）
                constraint_shape.constraintType.set(1)  # 链条
                
                # 设置约束位置
                constraint_transform.setTranslation(connection_point, space='world')
                
                try:
                    # 优化约束参数
                    if hasattr(constraint_shape, 'dampingLinear'):
                        constraint_shape.dampingLinear.set(0.6)
                    if hasattr(constraint_shape, 'dampingAngular'):
                        constraint_shape.dampingAngular.set(0.4)
                    
                    print(f"约束 {i+1} 已创建: {piece_a.name()} <-> {piece_b.name()}")
                        
                except Exception as e:
                    print(f"约束属性设置警告: {e}")
            
        pm.select(cl=True)
        print("链条约束设置完毕。")

    def _setup_simulation_environment(self):
        """设置优化参数"""
        if pm.objExists('bulletSolverShape1'):
            solver = pm.PyNode('bulletSolverShape1')
            
            try:
                # 优化求解器设置
                if hasattr(solver, 'subSteps'):
                    solver.subSteps.set(6)  # 增加子步数提高精度
                if hasattr(solver, 'solverIterations'):
                    solver.solverIterations.set(25)  # 增加迭代次数
                if hasattr(solver, 'gravity'):
                    solver.gravity.set([0, -9.81, 0])
                if hasattr(solver, 'enableContinuousCollisionDetection'):
                    solver.enableContinuousCollisionDetection.set(True)
                
                # 添加连续碰撞设置
                if hasattr(solver, 'contactProcessingThreshold'):
                    solver.contactProcessingThreshold.set(0.01)
                
                print("参数已调整成功。")
            except Exception as e:
                print(f"求解器属性设置警告: {e}")
   
    def _create_controller_for_link(self, target_link, controls_group):
        """为一个指定的链环创建控制器，并建立连接"""
        # 1. 将目标链环设置为运动学刚体
        try:
            rb_shape = target_link.getShape().connections(type='bulletRigidBodyShape')[0]
            rb_shape.bodyType.set(1)  # 1 = Kinematic
        except IndexError:
            pm.warning(f"无法为'{target_link.name()}'找到bullet刚体形状。")
            return None

        # 2. 创建一个NURBS圆环作为控制器
        controller = pm.circle(name=f"{target_link.name()}_ctrl", normal=(0, 1, 0), radius=0.5)[0]
        
        # 3. 将控制器移动并对齐到目标链环的位置和方向
        #   - 先创建一个临时的父子约束（无偏移）来对齐
        temp_constraint = pm.parentConstraint(target_link, controller, maintainOffset=False)
        #   - 对齐后即可删除约束，控制器已在正确位置
        pm.delete(temp_constraint)

        # 4. 创建正式的约束：让控制器驱动链环
        #   - 这次是控制器作为“父”，链环作为“子”
        pm.parentConstraint(controller, target_link, maintainOffset=True)

        # 5. 将控制器放入指定的控制器组中，便于查看整理
        pm.parent(controller, controls_group)
        
        print(f"为'{target_link.name()}'创建了控制器'{controller.name()}'")
        return controller

# ===================================================================
# 运行该脚本
# ===================================================================
if __name__ == "__main__":
    tool = ChainGeneratorUI()
    tool.create_ui()