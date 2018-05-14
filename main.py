# -*- coding:utf8 -*-

# this file uses multi cross input

import warnings
import pandas as pd
import numpy as np
import time
from sklearn.tree import DecisionTreeRegressor
from sklearn.preprocessing import MinMaxScaler
from math import radians, cos, sin, asin, sqrt
import common_tool as CT

path_train = "/data/dm/train.csv"  # 训练文件
path_test = "/data/dm/test.csv"  # 测试文件
path_test_out = "model/"  # 预测结果输出路径为model/xx.csv,有且只能有一个文件并且是CSV格式。
columns_name = ['TERMINALNO', 'TIME', 'TRIP_ID', 'LONGITUDE', 'LATITUDE', 'DIRECTION'\
        ,'HEIGHT', 'SPEED', 'CALLSTATE','Y']

def split_users(data, iteration):
    '''
    使Y=0和Y!=0的样本相等，最后一次使用剩下的全部样本
    :param data: 数据
    :param iteration: 第几次迭代
    :return:
    '''
    y_user = data[data.Y !=0].reset_index(drop=True)
    noy_user = data[data.Y == 0].reset_index(drop=True)

    if iteration != 5: # 最后一次
        selected_noy_user = noy_user.loc[iteration*len(y_user): (iteration+1)*len(y_user)]
    else:
        selected_noy_user = noy_user.loc[iteration*len(y_user):len(noy_user)]

    new_data = pd.concat([y_user,selected_noy_user])

    return new_data

def haversine(data):  # 经度1，纬度1，经度2，纬度2 （十进制度数）
    """
    计算两个经纬度之间的距离,将十进制度数转化为弧度
    """
    lon1, lat1, lon2, lat2 = map(radians, list(data))
    # haversine公式
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # 地球平均半径，单位为公里
    return c * r * 1000

def difference(datavector):
    difference[1:] = datavector[1:] - datavector[:-1]
    difference[0] = 0
    return difference

def strategy(data):
    print(data.info(memory_usage = 'deep'))
    mean_value = data['SPEED'][data.SPEED != -1].mean()  # 去掉缺失值之后的均值
    data.SPEED = data['SPEED'].replace([-1], [mean_value])  # 均值速度填充缺失值

    # 修改callstate的状态为-1,2,3,4-没打电话，打电话，打电话和没打电话
    data.CALLSTATE = data['CALLSTATE'].replace([-1, 2, 3, 4], [0, 1, 1, 0])

    # 中国经度73~135之间, # 中国维度20~53之间, # 删除方向丢失的数据,# 中国高度20~53之间
    data = data[(73 < data.LONGITUDE) & (data.LONGITUDE < 135) \
                & (18 < data.LATITUDE) & (data.LATITUDE < 53) \
                & (data.DIRECTION != -1) \
                & (-150 < data.HEIGHT) & (data.HEIGHT < 6700)]

    data['MINMAX_HEIGHT'] = MinMaxScaler().fit_transform(data[['HEIGHT']])[:, 0]  # test height
    data['MINMAX_SPEED'] = MinMaxScaler().fit_transform(data[['SPEED']])[:, 0]  # test height

    data = data.sort_values(by=['TERMINALNO', 'TRIP_ID', 'TIME']).reset_index(drop=True)

    data_times = data['TIME'].map(time.localtime)
    hours = list(map(lambda t: t[3], list(data_times)))  # 获取驾驶的时间- 在某个小时
    data['DRIVING_HOURS'] = hours
    data['TIRED_DRIVING'] = hours  # 是否是疲劳驾驶

    data.loc[((data.TIRED_DRIVING >= 0) & (data.TIRED_DRIVING <= 3) | \
              (data.TIRED_DRIVING >= 18) & (data.TIRED_DRIVING <= 20)), 'TIRED_DRIVING'] = 1  # 是疲劳驾驶
    data.loc[((data.TIRED_DRIVING >= 3) & (data.TIRED_DRIVING <= 18) | \
              (data.TIRED_DRIVING >= 20) & (data.TIRED_DRIVING <= 23)), 'TIRED_DRIVING'] = 2  # 不是疲劳驾驶

    # 判断打电话时的速度
    data['SPEED_DIFFERENCE'] = data[['SPEED']].diff()
    data['HEIGHT_DIFFERENCE'] = data[['HEIGHT']].diff()
    data['DIR_DIFFERENCE'] = data[['DIRECTION']].diff()
    data.loc[(data.DIR_DIFFERENCE <= -180), 'DIR_DIFFERENCE'] = \
        data.loc[(data.DIR_DIFFERENCE < -180), 'DIR_DIFFERENCE'] + 360
    data.loc[(data.DIR_DIFFERENCE >= 180), 'DIR_DIFFERENCE'] = \
        data.loc[(data.DIR_DIFFERENCE >= 180), 'DIR_DIFFERENCE'] - 360
    trip_index = data.groupby(by=['TERMINALNO', 'TRIP_ID']).apply(lambda x: x.index[0]).sort_values()
    data.loc[trip_index, 'SPEED_DIFFERENCE'] = 0
    data.loc[trip_index, 'HEIGHT_DIFFERENCE'] = 0
    data.loc[trip_index, 'DIR_DIFFERENCE'] = 0
    data['SHAPE_TURN'] = data['SPEED_DIFFERENCE']  # 转弯时速度
    data.loc[(np.abs(data.DIR_DIFFERENCE) < 90), 'SHAPE_TURN'] = 0
    data.loc[(np.abs(data.DIR_DIFFERENCE) >= 90), 'SHAPE_TURN'] = 1
    data.loc[(data.SPEED < 15), 'SHAPE_TURN'] = 0
    data['CALL_LEFT'] = data['CALLSTATE']
    data['CALL_RIGHT'] = data['CALLSTATE']

    data.loc[data.DIR_DIFFERENCE >= -30, 'CALL_LEFT'] = 0
    data.loc[data.DIR_DIFFERENCE <= 30, 'CALL_RIGHT'] = 0
    data['SLOPE'] = data['HEIGHT_DIFFERENCE']
    data.loc[(data.SPEED == 0), 'SLOPE'] = 0
    data.loc[(data.SPEED != 0), 'SLOPE'] = data['SLOPE'] / (data['SPEED'] * 16.67)

    group_data = data.groupby(by=['TERMINALNO', 'TRIP_ID'])

    max_group_data = group_data.max()
    min_group_data = group_data.min()
    mean_group_data = group_data.mean()
    sum_group_data = group_data.sum()

    new_data = pd.DataFrame()
    new_data['TIRED_DRIVING'] = max_group_data.TIRED_DRIVING  # 疲劳驾驶最长时间
    new_data['TIRED_DRIVING_TIMES'] = data[['TERMINALNO', 'TRIP_ID', 'TIRED_DRIVING']] \
        .groupby(by=['TERMINALNO', 'TRIP_ID']).apply(lambda x: len(x) - x.count(0)).TIRED_DRIVING  # 疲劳驾驶次数
    new_data['DRIVING_HOURS'] = data[['TERMINALNO', 'TRIP_ID', 'TIRED_DRIVING']] \
        .groupby(by=['TERMINALNO', 'TRIP_ID']).agg(lambda x: np.mean(pd.Series.mode(x)))  # 最经常驾驶时间
    new_data['MAX_LON'] = max_group_data.LONGITUDE  # 最大纬度
    new_data['MIN_LON'] = min_group_data.LONGITUDE  # 最大纬度
    new_data['MEAN_LON'] = mean_group_data.LONGITUDE  # 平均纬度

    new_data['MAX_LAT'] = max_group_data.LATITUDE  # 最大经度
    new_data['MIN_LAT'] = min_group_data.LATITUDE  # 最大经度
    new_data['MEAN_LAT'] = mean_group_data.LATITUDE  # 最大经度

    new_data['CALL_TIMES'] = sum_group_data.CALLSTATE  # 打电话总次数

    run_range = new_data[['MAX_LON', 'MAX_LAT', 'MIN_LON', 'MIN_LAT']] \
        .apply(haversine, axis=1)  # 对每行使用haversine函数，计算最大行驶范围
    new_data['RUN_RANGE'] = run_range

    new_data['TTD'] = group_data.sum().SPEED.values * 50 / 3  # 行驶路程

    new_data['MAX_SPEED'] = min_group_data.SPEED  # 最大速度
    new_data['MIN_SPEED'] = max_group_data.SPEED  # 最小速度
    new_data['MEAN_SPEED'] = mean_group_data.SPEED  # 平均速度

    # new_data['MAX_MINMAX_SPEED'] = min_group_data.MINMAX_HEIGHT  # 最大正则化速度
    # new_data['MIN_MINMAX_SPEED'] = max_group_data.MINMAX_HEIGHT  # 最小正则化速度
    # new_data['MEAN_MINMAX_SPEED'] = mean_group_data.MINMAX_HEIGHT  # 平均正则化速度

    new_data['MAX_SPEED_DIFFERENCE'] = min_group_data.SPEED_DIFFERENCE  # 最大瞬时速度差
    new_data['MIN_SPEED_DIFFERENCE'] = max_group_data.SPEED_DIFFERENCE  # 最小瞬时速度差
    new_data['MEAN_SPEED_DIFFERENCE'] = mean_group_data.SPEED_DIFFERENCE  # 平均瞬时速度差

    new_data['MAX_HEIGHT_DIFFERENCE'] = min_group_data.HEIGHT_DIFFERENCE  # 最大瞬时高度差
    new_data['MIN_HEIGHT_DIFFERENCE'] = max_group_data.HEIGHT_DIFFERENCE  # 最小瞬时高度差
    new_data['MEAN_HEIGHT_DIFFERENCE'] = mean_group_data.HEIGHT_DIFFERENCE  # 平均瞬时高度差

    new_data['MAX_DIR_DIFFERENCE'] = min_group_data.DIR_DIFFERENCE  # 最大瞬时方向差
    new_data['MIN_DIR_DIFFERENCE'] = max_group_data.DIR_DIFFERENCE  # 最小瞬时方向差
    new_data['MEAN_DIR_DIFFERENCE'] = mean_group_data.DIR_DIFFERENCE  # 平均瞬时方向差

    new_data['SHAPE_TURN'] = max_group_data.SHAPE_TURN  # 是否急转弯
    new_data['SHAPE_TURN_TIMES'] = sum_group_data.SHAPE_TURN  # 急转弯总次数

    new_data['CALL_LEFT'] = max_group_data.CALL_LEFT  # 是否打电话左转
    new_data['CALL_LEFT_TIME'] = sum_group_data.CALL_LEFT  # 打电话左转总次数

    new_data['CALL_RIGHT'] = max_group_data.CALL_RIGHT  # 是否打电话右转
    new_data['CALL_RIGHT_TIME'] = sum_group_data.CALL_RIGHT  # 打电话右转总次数

    new_data['MAX_SLOPE'] = min_group_data.SLOPE  # 最大瞬时坡度差
    new_data['MIN_SLOPE'] = max_group_data.SLOPE  # 最小瞬时坡度差
    new_data['MEAN_SLOPE'] = mean_group_data.SLOPE  # 平均瞬时坡度差

    # 创造是否长时间驾驶的特征
    data['TIME_DIFF'] = data[['TIME']].diff()
    first_trip_index = data.groupby(by=['TERMINALNO']).apply(lambda x: x.index[0]).sort_values()
    data.loc[first_trip_index, 'TIME_DIFF'] = 0  # 设置每个用户的第一条数据的时间差是0

    index = data[(data.TIME_DIFF >= 600) | (data.TIME_DIFF == 0)].index.tolist()  # 间隔十分钟，用户的第一条数据
    index.append(data.index.tolist()[-1])

    for i in range(1, len(index)):
        new_data.loc[index[i - 1]:index[i], 'LONG_DRIVING_TIME'] = len(data.loc[index[i - 1]:index[i] - 1]) / 60.0

    # 加上用户ID
    user_trip = list(group_data.indices.keys())
    new_data['TERMINALNO'] = list(map(lambda x: x[1], user_trip))

    if 'Y' in data.columns.tolist():
        new_data['Y'] = mean_group_data.Y

    return new_data

def print_memory(data):
    for dtype in ['float','int','object']:
        selected_type  = data.select_dtypes(include=[dtype])
        mean_usage_b = selected_type.memory_usage(deep=True).mean()
        mean_usage_mb = mean_usage_b/1024 *2
        print('mean_memory_is_for {} columns: {:03.2f} MB'.format(dtype,mean_usage_mb))

def process():
    ## train
    ## 改成多线程
    reader = pd.read_csv(path_train, chunksize=8000000)
    origin_train_data = None
    for i,chunk in enumerate(reader):
        temp_train_df = strategy(chunk)
        if origin_train_data is None:
            origin_train_data = temp_train_df
        else:
            origin_train_data.append(temp_train_df)

    #test
    reader = pd.read_csv(path_test, chunksize=10000000)
    origin_test_data = None
    for chunk in reader:
        print('test_chunk')
        temp_test_df = strategy(chunk)
        if origin_test_data is None:
            origin_test_data = temp_test_df
        else:
            origin_test_data.append(temp_test_df)

    # 6:1 训练分类器
    print('training:')
    test_data = origin_test_data[['TERMINALNO']]
    final_res = test_data[['TERMINALNO']]
    estimator = DecisionTreeRegressor()# 决策树分类器
    for iteration in range(6):# Y=0-6:1-Y!=0
        train_data = split_users(origin_train_data, iteration=iteration)#分割训练样本
        estimator.fit(train_data.drop('Y',axis=1).values, train_data['Y'].values)
        predict_label = estimator.predict(origin_test_data.values)
        if iteration == 0:
            final_res['Pred'] = predict_label
        else:
            final_res['Pred'] = final_res['Pred'].values + predict_label
    final_res['Pred'] = final_res.Pred.values / 6
    final_max_res = final_res[['TERMINALNO','Pred']].groupby('TERMINALNO').max()
    final_max_res = CT.process_y0(final_max_res) # 处理结果为0的y值
    CT.write_result(final_max_res.index.values, final_max_res['Pred'].values)

if __name__ == "__main__":
    start = time.clock()# 计时器
    warnings.filterwarnings("ignore")
    process()
    print('whole_time:' +  str(round(time.clock() - start,2)))