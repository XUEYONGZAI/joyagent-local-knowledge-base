import { useEffect, useState, useRef, useMemo } from "react";
import {
  getUniqId,
  scrollToTop,
  ActionViewItemEnum,
  getSessionId,
} from "@/utils";
import querySSE from "@/utils/querySSE";
import { handleTaskData, combineData } from "@/utils/chat";
import Dialogue from "@/components/Dialogue";
import DataDialogue from "@/components/Dialogue/DataDialogue";
import GeneralInput from "@/components/GeneralInput";
import ActionView from "@/components/ActionView";
import { RESULT_TYPES } from "@/utils/constants";
import { useMemoizedFn } from "ahooks";
import classNames from "classnames";
import Logo from "../Logo";
import { Modal } from "antd";

type Props = {
  inputInfo: CHAT.TInputInfo;
  product?: CHAT.Product;
};

const ChatView: GenieType.FC<Props> = (props) => {
  const { inputInfo: inputInfoProp, product } = props;

  const [chatTitle, setChatTitle] = useState("");
  const [taskList, setTaskList] = useState<MESSAGE.Task[]>([]);
  const chatList = useRef<CHAT.ChatItem[]>([]);
  const [dataChatList, setDataChatList] = useState<Record<string, any>[]>([]);
  const [activeTask, setActiveTask] = useState<CHAT.Task>();
  const [plan, setPlan] = useState<CHAT.Plan>();
  const [showAction, setShowAction] = useState(false);
  const [loading, setLoading] = useState(false);
  const chatRef = useRef<HTMLInputElement>(null);
  const actionViewRef = ActionView.useActionView();
  const sessionId = useMemo(() => getSessionId(), []);
  const [modal, contextHolder] = Modal.useModal();

  const combineCurrentChat = (
    inputInfo: CHAT.TInputInfo,
    sessionId: string,
    requestId: string
  ): CHAT.ChatItem => {
    return {
      query: inputInfo.message!,
      files: inputInfo.files!,
      responseType: "txt",
      sessionId,
      requestId,
      loading: true,
      forceStop: false,
      tasks: [],
      thought: "",
      response: "",
      taskStatus: 0,
      tip: "已接收到你的任务，将立即开始处理...",
      multiAgent: { tasks: [] },
    };
  };

  const sendMessage = useMemoizedFn((inputInfo: CHAT.TInputInfo) => {
    const { message, deepThink, outputStyle } = inputInfo;
    const requestId = getUniqId();
    let currentChat = combineCurrentChat(inputInfo, sessionId, requestId);
    chatList.current = [...chatList.current, currentChat];
    if (!chatTitle) {
      setChatTitle(message!);
    }
    setLoading(true);
    const params = {
      sessionId: sessionId,
      requestId: requestId,
      query: message,
      deepThink: deepThink ? 1 : 0,
      outputStyle,
    };
    const handleMessage = (data: MESSAGE.Answer) => {
      const { finished, resultMap, packageType, status } = data;
      if (status === "tokenUseUp") {
        modal.info({
          title: "您的试用次数已用尽",
          content: "如需额外申请，请联系 liyang.1236@jd.com",
        });
        const taskData = handleTaskData(
          currentChat,
          deepThink,
          currentChat.multiAgent
        );
        currentChat.loading = false;
        setLoading(false);

        setTaskList(taskData.taskList);
        return;
      }
      if (packageType !== "heartbeat") {
        requestAnimationFrame(() => {
          if (resultMap?.eventData) {
            currentChat = combineData(resultMap.eventData || {}, currentChat);
            const taskData = handleTaskData(
              currentChat,
              deepThink,
              currentChat.multiAgent
            );
            setTaskList(taskData.taskList);
            temporaryChangeTask(taskData.taskList);
            updatePlan(taskData.plan!);
            openAction(taskData.taskList);
            if (finished) {
              currentChat.loading = false;
              setLoading(false);
            }
            const newChatList = [...chatList.current];
            newChatList.splice(newChatList.length - 1, 1, currentChat);
            chatList.current = newChatList;
          }
        });
        scrollToTop(chatRef.current!);
      }
    };

    const openAction = (taskList: MESSAGE.Task[]) => {
      if (
        taskList.filter((t) => !RESULT_TYPES.includes(t.messageType)).length
      ) {
        setShowAction(true);
      }
    };

    const handleError = (error: unknown) => {
      throw error;
    };

    const handleClose = () => {
      console.log("🚀 ~ close");
    };

    querySSE(
      {
        body: params,
        handleMessage,
        handleError,
        handleClose,
      }
    );
  });

  const temporaryChangeTask = (taskList: MESSAGE.Task[]) => {
    const task = taskList[taskList.length - 1] as CHAT.Task;
    if (!["task_summary", "result"].includes(task?.messageType)) {
      setActiveTask(task);
    }
  };

  const changeTask = (task: CHAT.Task) => {
    actionViewRef.current?.changeActionView(ActionViewItemEnum.follow);
    changeActionStatus(true);
    setActiveTask(task);
  };

  const updatePlan = (plan: CHAT.Plan) => {
    setPlan(plan);
  };

  const changeFile = (file: CHAT.TFile) => {
    changeActionStatus(true);
    actionViewRef.current?.setFilePreview(file);
  };

  const changePlan = () => {
    changeActionStatus(true);
    actionViewRef.current?.openPlanView();
  };

  const changeActionStatus = (status: boolean) => {
    setShowAction(status);
  };

  const sendDataMessage = (inputInfo: any) => {
    console.log("🚀 sendDataMessage 被调用", inputInfo);
    const requestId = getUniqId();
    const params = {
      sessionId: sessionId,
      requestId: requestId,
      query: inputInfo.message,
      deepThink: 0,
      outputStyle: inputInfo.outputStyle,
    };
    console.log("📤 发送请求:", params);
    const currentChat = {
      query: inputInfo.message,
      loading: true,
      think: "",
      chartData: undefined,
      error: "",
      response: "",
    };
    setDataChatList([...dataChatList, currentChat]);
    scrollToTop(chatRef.current!);

    setChatTitle(inputInfo.message);
    setLoading(true);

    const handleMessage = (data: any) => {
      console.log("📨 收到消息:", data);
      switch (data.packageType) {
        case "heartbeat":
          break;
        case "result":
          currentChat.response = data.response;
          currentChat.chartData = data.resultMap;
          currentChat.loading = false;
          setLoading(false);
          break;
        default:
          break;
      }
      const newChatList = [...dataChatList];
      newChatList.splice(newChatList.length - 1, 1, currentChat);
      setDataChatList(newChatList);
      scrollToTop(chatRef.current!);
    };
    const handleError = (error: unknown) => {
      currentChat.loading = false;
      currentChat.error = String(error);
      setLoading(false);
      const newChatList = [...dataChatList];
      newChatList.splice(newChatList.length - 1, 1, currentChat);
      setDataChatList(newChatList);
      throw error;
    };

    const handleClose = () => {
      console.log("🚀 ~ close - 更新 UI");
      currentChat.loading = false;
      setLoading(false);
      const newChatList = [...dataChatList];
      console.log("📋 newChatList before:", newChatList.length);
      newChatList.splice(newChatList.length - 1, 1, currentChat);
      console.log("📋 newChatList after:", newChatList.length);
      setDataChatList(newChatList);
    };
    querySSE(
      {
        body: params,
        handleMessage,
        handleError,
        handleClose,
      },
      SERVICE_BASE_URL ? `${SERVICE_BASE_URL}/web/api/v1/gpt/queryAgentStreamIncr` : '/web/api/v1/gpt/queryAgentStreamIncr'
    );
  };

  useEffect(() => {
    if (inputInfoProp.message?.length !== 0) {
      product?.type === "dataAgent" && !inputInfoProp.deepThink
        ? sendDataMessage(inputInfoProp)
        : sendMessage(inputInfoProp);
    }
  }, [inputInfoProp, sendMessage]);

  const renderMultAgent = () => {
    return (
      <div className="h-full w-full flex justify-center">
        <div
          className={classNames("p-24 flex flex-col flex-1 w-0", {
            "max-w-[1200px]": !showAction,
          })}
          id="chat-view"
        >
          <div className="w-full flex justify-between">
            <div className="w-full flex items-center pb-8">
              <Logo />
              <div className="overflow-hidden whitespace-nowrap text-ellipsis text-[16px] font-[500] text-[#27272A] mr-8">
                {chatTitle}
              </div>
              {inputInfoProp.deepThink && (
                <div className="rounded-[4px] px-6 border-1 border-solid border-gray-300 flex items-center shrink-0">
                  <i className="font_family icon-shendusikao mr-6 text-[12px]"></i>
                  <span className="ml-[-4px]">深度研究</span>
                </div>
              )}
            </div>
          </div>
          <div
            className="w-full flex-1 overflow-auto no-scrollbar mb-[36px]"
            ref={chatRef}
          >
            {chatList.current.map((chat) => {
              return (
                <div key={chat.requestId}>
                  <Dialogue
                    chat={chat}
                    deepThink={inputInfoProp.deepThink}
                    changeTask={changeTask}
                    changeFile={changeFile}
                    changePlan={changePlan}
                  />
                </div>
              );
            })}
          </div>
          <GeneralInput
            placeholder={
              loading ? "任务进行中" : "希望 Genie 为你做哪些任务呢？"
            }
            showBtn={false}
            size="medium"
            disabled={loading}
            product={product}
            // 多轮问答也不支持切换deepThink，使用传进来的
            send={(info) =>
              sendMessage({
                ...info,
                deepThink: inputInfoProp.deepThink,
              })
            }
          />
        </div>
        {contextHolder}
        <div
          className={classNames("transition-all w-0", {
            "opacity-0 overflow-hidden": !showAction,
            "flex-1": showAction,
          })}
        >
          <ActionView
            activeTask={activeTask}
            taskList={taskList}
            plan={plan}
            ref={actionViewRef}
            onClose={() => changeActionStatus(false)}
          />
        </div>
      </div>
    );
  };

  const renderDataAgent = () => {
    return (
      <div
        className={classNames("p-24 flex flex-col flex-1 w-0 max-w-[1200px]")}
      >
        <div className="w-full flex justify-between">
          <div className="w-full flex items-center pb-8">
            <Logo />
            <div className="overflow-hidden whitespace-nowrap text-ellipsis text-[16px] font-[500] text-[#27272A] mr-8">
              {chatTitle}
            </div>
          </div>
        </div>
        <div
          className="w-full flex-1 overflow-auto no-scrollbar mb-[36px]"
          ref={chatRef}
        >
          {dataChatList.map((chat, index) => {
            return (
              <div key={index}>
                <DataDialogue chat={chat} />
              </div>
            );
          })}
        </div>
        <GeneralInput
          placeholder={loading ? "任务进行中" : "希望 Genie 为你做哪些任务呢？"}
          showBtn={false}
          size="medium"
          disabled={loading}
          product={product}
          send={(info) =>
            sendDataMessage({
              ...info,
            })
          }
        />
      </div>
    );
  };

  return (
    <div className="h-full w-full flex justify-center">
      {product?.type === "dataAgent" && !inputInfoProp.deepThink
        ? renderDataAgent()
        : renderMultAgent()}
    </div>
  );
};

export default ChatView;
