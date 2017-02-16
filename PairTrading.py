# -*- coding:utf-8 -*-

from CloudQuant import MiniSimulator
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.tsa.stattools as ts

username = 'Harvey_Sun'
password = 'P948894dgmcsy'
Strategy_Name = 'PairTrading_2_0_13'

INIT_CAP = 100000000
START_DATE = '20130101'
END_DATE = '20161231'
fee_rate = 0.000
base_port = 0.8

k1 = 0
k2 = 2
k3 = 6


def coint(x, y):
    '''
    检验两个序列是否协整
    :param x: Series, array
    :param y: Series, array
    :return: True or False
    '''
    xs = sm.add_constant(x)
    reg = sm.OLS(y, xs)
    outcome = reg.fit()
    residual = outcome.resid
    pvalue = ts.adfuller(residual)[1]
    if pvalue < 0.05:
        return True
    else:
        return False


def initial(sdk):
    sdk.prepareData(['LZ_GPA_QUOTE_TCLOSE', 'LZ_GPA_SLCIND_STOP_FLAG', 'LZ_GPA_INDU_SW'])
    mei_tan = ['600121','600123','600188','600348','600395','600508','600997','601001','601088','601666','601699','601918','000937','000968','000983']

    stock_list = sdk.getStockList()
    close = pd.DataFrame(sdk.getFieldData('LZ_GPA_QUOTE_TCLOSE')[-100:], columns=stock_list)
    not_stop = pd.DataFrame(sdk.getFieldData('LZ_GPA_SLCIND_STOP_FLAG')[-100:], columns=stock_list)
    # not_stop_stocks = pd.Series(stock_list)[list(np.logical_and(close.notnull().all(axis=0), not_stop.isnull().all(axis=0)))]
    not_stop_stocks = pd.Series(stock_list)[list(close.notnull().all(axis=0))]
    mei_tan_not_stop = list(set(mei_tan) & set(not_stop_stocks))
    pairs = []
    for i in mei_tan_not_stop:
        for j in mei_tan_not_stop:
            if mei_tan_not_stop.index(j) > mei_tan_not_stop.index(i):
                pair = [i, j, coint(close[i], close[j])]
                pairs.append(pair)
    pairs = pd.DataFrame(pairs, columns=['stock_x', 'stock_y', 'coint'])
    coint_pairs = pairs[pairs['coint']]
    coint_dict = dict()
    position = dict()
    for i in coint_pairs.index:
        coint_dict[str(i)] = {'stock_x': coint_pairs['stock_x'][i], 'stock_y': coint_pairs['stock_y'][i]}
        position[str(i)] = {'position': 0, 'position_x':0, 'position_y':0}
    sdk.setGlobal('coint_dict', coint_dict)
    temp = pd.Series(list(coint_pairs['stock_x']) + list(coint_pairs['stock_y'])).value_counts()
    one_unit = INIT_CAP * base_port / temp.sum()
    sdk.setGlobal('one_unit', one_unit)
    sdk.setGlobal('unit_num', temp)
    sdk.setGlobal('position', position)


def init_per_day(sdk):
    unit_num = sdk.getGlobal('unit_num')
    stock_list = sdk.getStockList()
    coint_dict = sdk.getGlobal('coint_dict')
    close = pd.DataFrame(sdk.getFieldData('LZ_GPA_QUOTE_TCLOSE')[-100:], columns=stock_list)[unit_num.index]
    signals = dict()
    for i in coint_dict.keys():
        stock_x = coint_dict[i]['stock_x']
        stock_y = coint_dict[i]['stock_y']
        x = close[stock_x]
        y = close[stock_y]
        xs = sm.add_constant(x)
        reg = sm.OLS(y, xs)
        outcome = reg.fit()
        residual = outcome.resid
        coef = outcome.params[1]
        var = residual.std()
        last_resid = residual.iloc[-1]
        signals[i] = [stock_x, stock_y, var, last_resid, coef]
    sdk.setGlobal('signals', signals)


def strategy(sdk):
    if sdk.getNowDate() == '20080602':
        one_unit = sdk.getGlobal('one_unit')
        unit_num = sdk.getGlobal('unit_num')
        quotes = sdk.getQuotes(list(unit_num.index))
        build_base = []
        one_unit_volumes = []
        for stock in unit_num.index:
            open = quotes[stock].open
            one_unit_volume = int(one_unit / (100 * open)) * 100
            volume = int(one_unit / (100 * open)) * unit_num[stock] * 100
            order = [stock, open, volume, 1]
            one_unit_volumes.append(one_unit_volume)
            sdk.makeOrder(stock, open, volume, 1)
        # sdk.makeOrders(build_base)
        one_unit_volumes = pd.Series(one_unit_volumes, index=unit_num.index)
        sdk.setGlobal('one_unit_volumes', one_unit_volumes)


    if sdk.getNowDate() > '20080602':
        one_unit_volumes = sdk.getGlobal('one_unit_volumes')
        signals = sdk.getGlobal('signals')
        position = sdk.getGlobal('position')
        quotes = sdk.getQuotes(list(one_unit_volumes.index))
        orders = []
        for i in signals.keys():
            stock_x, stock_y, var, last_resid, coef = signals[i]
            position_i = position[i]
            open_y = quotes[stock_y].open
            open_x = quotes[stock_x].open
            if (k2 * var < last_resid <= k3 * var) & (position_i['position'] == 0):
                if int(one_unit_volumes[stock_y] * round(coef, 2) / 100) * 100 <= one_unit_volumes[stock_x]:
                    volume_y = one_unit_volumes[stock_y]
                    volume_x = int(one_unit_volumes[stock_y] * round(coef, 2) / 100) * 100
                else:
                    volume_x = one_unit_volumes[stock_x]
                    volume_y = int(one_unit_volumes[stock_x] / round(coef,2) / 100) * 100
                order_y = [stock_y, open_y, volume_y, -1]
                order_x = [stock_x, open_x, volume_x, 1]
                sdk.makeOrder(stock_y, open_y, volume_y, -1)
                sdk.makeOrder(stock_x, open_x, volume_x, 1)
                orders.append(order_y)
                orders.append(order_x)
                position[i]['position'] = -1
                position[i]['stock_x'] = open_x
                position[i]['stock_y'] = open_y
            elif (-k2 * var > last_resid >= -k3 * var) & (position_i['position'] == 0):
                if int(one_unit_volumes[stock_y] * round(coef, 2) / 100) * 100 <= one_unit_volumes[stock_x]:
                    volume_y = one_unit_volumes[stock_y]
                    volume_x = int(one_unit_volumes[stock_y] * round(coef, 2) / 100) * 100
                else:
                    volume_x = one_unit_volumes[stock_x]
                    volume_y = int(one_unit_volumes[stock_x] / round(coef,2) / 100) * 100
                order_y = [stock_y, open_y, volume_y, 1]
                order_x = [stock_x, open_x, volume_x, -1]
                sdk.makeOrder(stock_x, open_x, volume_x, -1)
                sdk.makeOrder(stock_y, open_y, volume_y, 1)
                orders.append(order_y)
                orders.append(order_x)
                position[i]['position'] = 1
                position[i]['stock_x'] = open_x
                position[i]['stock_y'] = open_y
            elif (last_resid <= k1 * var) & (position_i['position'] == -1):
                volume_y = position[i]['stock_y']
                volume_x = position[i]['stock_x']
                order_y = [stock_y, open_y, volume_y, 1]
                order_x = [stock_x, open_x, volume_x, -1]
                sdk.makeOrder(stock_x, open_x, volume_x, -1)
                sdk.makeOrder(stock_y, open_y, volume_y, 1)
                orders.append(order_y)
                orders.append(order_x)
                position[i]['position'] = 0
                position[i]['stock_x'] = 0
                position[i]['stock_y'] = 0
            elif (last_resid >= -k1 * var) & (position_i['position'] == 1):
                volume_y = position[i]['stock_y']
                volume_x = position[i]['stock_x']
                order_y = [stock_y, open_y, volume_y, -1]
                order_x = [stock_x, open_x, volume_x, 1]
                sdk.makeOrder(stock_y, open_y, volume_y, -1)
                sdk.makeOrder(stock_x, open_x, volume_x, 1)
                orders.append(order_y)
                orders.append(order_x)
                position[i]['position'] = 0
                position[i]['stock_x'] = 0
                position[i]['stock_y'] = 0
            else:
                pass
        # sdk.makeOrders(orders)
        sdk.sdklog(sdk.getNowDate(), '=============日期')
        sdk.sdklog(np.array(orders))


config = {
    'username': username,
    'password': password,
    'initCapital': INIT_CAP,
    'startDate': START_DATE,
    'endDate': END_DATE,
    'strategy': strategy,
    'preparePerDay': init_per_day,
    'initial': initial,
    'feeRate': fee_rate,
    'strategyName': Strategy_Name,
    'logfile': '%s.log' % Strategy_Name,
    'rootpath': 'C:/cStrategy/',
    'executeMode': 'D',
    'feeLimit': 5,
    'cycle': 1,
    'dealByVolume': True,
    'allowForTodayFactors': ['LZ_GPA_SLCIND_STOP_FLAG']
}

if __name__ == "__main__":
    # 在线运行所需代码
    import os
    config['strategyID'] = os.path.splitext(os.path.split(__file__)[1])[0]
    MiniSimulator(**config).run()
