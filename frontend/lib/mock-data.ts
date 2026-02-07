import type { Paper, ProcessingStatus } from "./types";

// Public sample video for local UI testing.
// Source: MDN (CC0)
const SAMPLE_VIDEO =
  "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4";

export const MOCK_PAPER: Paper = {
  paper_id: "1706.03762",
  title: "Attention Is All You Need",
  authors: ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"],
  abstract:
    "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. We propose the Transformer, a model architecture relying entirely on attention mechanisms to draw global dependencies between input and output.",
  pdf_url: "https://arxiv.org/pdf/1706.03762.pdf",
  html_url: "https://arxiv.org/abs/1706.03762",
  sections: [
    {
      id: "s-intro",
      title: "1. Motivation",
      content:
        "The dominant sequence transduction models are based on complex **recurrent** or **convolutional** neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an *attention mechanism*.\n\nWe propose a new simple network architecture, the **Transformer**, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
      level: 1,
      order_index: 0,
      equations: [],
    },
    {
      id: "s-attn",
      title: "2. The Attention Mechanism",
      content:
        "An attention function can be described as mapping a query and a set of key-value pairs to an output. The output is computed as a weighted sum of the values, where the weight assigned to each value is computed by a compatibility function of the query with the corresponding key.\n\nWe call our particular attention **Scaled Dot-Product Attention**. The input consists of queries and keys of dimension $d_k$, and values of dimension $d_v$. We compute the dot products of the query with all keys, divide each by $\\sqrt{d_k}$, and apply a softmax function to obtain the weights on the values:\n\n$$\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$\n\nThe two most commonly used attention functions are additive attention and dot-product (multiplicative) attention. Dot-product attention is identical to our algorithm, except for the scaling factor of $\\frac{1}{\\sqrt{d_k}}$.",
      level: 1,
      order_index: 1,
      equations: [],
      video_url: SAMPLE_VIDEO,
    },
    {
      id: "s-mha",
      title: "2.1 Multi-Head Attention",
      content:
        "Instead of performing a single attention function with $d_{\\text{model}}$-dimensional keys, values and queries, we found it beneficial to linearly project the queries, keys and values $h$ times with different, learned linear projections to $d_k$, $d_k$ and $d_v$ dimensions, respectively.\n\nOn each of these projected versions we perform the attention function in parallel, yielding $d_v$-dimensional output values. These are concatenated and once again projected:\n\n$$\\text{MultiHead}(Q, K, V) = \\text{Concat}(\\text{head}_1, \\ldots, \\text{head}_h)W^O$$\n\nwhere each head is computed as:\n\n$$\\text{head}_i = \\text{Attention}(QW_i^Q, KW_i^K, VW_i^V)$$\n\nMulti-head attention allows the model to jointly attend to information from different representation subspaces at different positions.",
      level: 2,
      order_index: 2,
      equations: [],
    },
    {
      id: "s-ffn",
      title: "2.2 Position-wise Feed-Forward Networks",
      content:
        "In addition to attention sub-layers, each of the layers in our encoder and decoder contains a fully connected feed-forward network. This consists of two linear transformations with a ReLU activation in between:\n\n$$\\text{FFN}(x) = \\max(0, xW_1 + b_1)W_2 + b_2$$\n\nWhile the linear transformations are the same across different positions, they use different parameters from layer to layer. The dimensionality of input and output is $d_{\\text{model}} = 512$, and the inner-layer has dimensionality $d_{ff} = 2048$.",
      level: 2,
      order_index: 3,
      equations: [],
    },
    {
      id: "s-takeaways",
      title: "3. Takeaways",
      content:
        "The Transformer is the first transduction model relying entirely on self-attention to compute representations of its input and output without using sequence-aligned RNNs or convolution.\n\n**Key advantages:**\n- Reduced computational complexity per layer from $O(n^2 \\cdot d)$ to $O(n \\cdot d^2)$\n- Increased parallelization\n- Shorter path lengths between long-range dependencies\n\nFor very long sequences where $n > d$, self-attention can be restricted to a neighborhood of size $r$ in the input sequence, yielding a complexity of $O(r \\cdot n \\cdot d)$.",
      level: 1,
      order_index: 4,
      equations: [],
    },
  ],
};

export const MOCK_STATUS: ProcessingStatus = {
  job_id: "mock-job-123",
  status: "completed",
  progress: 1.0,
  sections_completed: 4,
  sections_total: 4,
  current_step: "Complete",
};

